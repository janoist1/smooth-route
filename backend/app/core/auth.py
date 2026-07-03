"""Clerk-backed authentication.

Flow: the frontend sends the Clerk session JWT as `Authorization: Bearer <t>`;
we verify it against the instance JWKS (RS256), then provision a local `users`
row just-in-time keyed on `clerk_id`. Role lives in our DB, not in Clerk.

The verifier is injectable (`set_token_verifier`) so tests can supply a fake
without any network or Clerk instance. AUTH_MODE=disabled short-circuits the
whole flow into a single-user admin identity for local development.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from fastapi import Depends, HTTPException, Request

from app.core.config import settings
from app.models.models import ROLE_ADMIN, User

logger = logging.getLogger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"


class TokenVerificationError(Exception):
    """Raised when a Bearer token is present but cannot be accepted."""


@dataclass(frozen=True)
class Identity:
    """Verified caller identity, resolved once per request."""

    user_id: str
    clerk_id: str
    email: Optional[str]
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class TokenVerifier(Protocol):
    def verify(self, token: str) -> dict[str, Any]:
        """Return the validated claims or raise TokenVerificationError."""
        ...


class ClerkJWKSVerifier:
    """Verifies Clerk session JWTs (RS256) against the instance JWKS.

    Clerk's default session token carries `sub` (clerk user id), `iss`, `azp`,
    `exp`, `iat`, `nbf` — but NO email unless the session token is customized
    in the dashboard. Email is therefore optional here and backfilled via the
    Backend API at provisioning time when CLERK_SECRET_KEY is available.
    """

    def __init__(
        self,
        jwks_url: str,
        issuer: Optional[str] = None,
        authorized_parties: Optional[list[str]] = None,
        leeway_seconds: float = 5.0,
    ):
        import jwt as pyjwt

        self._issuer = issuer
        self._authorized_parties = authorized_parties or []
        self._leeway = leeway_seconds
        # PyJWKClient caches keys; JWKS is only fetched on cache miss/rotation.
        self._jwk_client = pyjwt.PyJWKClient(jwks_url, cache_keys=True)

    def verify(self, token: str) -> dict[str, Any]:
        import jwt as pyjwt

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub"]},
            )
        except pyjwt.PyJWTError as exc:
            raise TokenVerificationError(f"Invalid token: {exc}") from exc

        azp = claims.get("azp")
        if self._authorized_parties and azp and azp not in self._authorized_parties:
            raise TokenVerificationError(f"Unauthorized party: {azp}")
        return claims


_token_verifier: Optional[TokenVerifier] = None


def set_token_verifier(verifier: Optional[TokenVerifier]) -> None:
    """Override the process-wide verifier (tests, custom deployments)."""
    global _token_verifier
    _token_verifier = verifier


def get_token_verifier() -> TokenVerifier:
    """Return the configured verifier, building the Clerk one lazily."""
    global _token_verifier
    if _token_verifier is None:
        jwks_url = settings.CLERK_JWKS_URL
        if not jwks_url and settings.CLERK_ISSUER:
            jwks_url = settings.CLERK_ISSUER.rstrip("/") + "/.well-known/jwks.json"
        if not jwks_url:
            raise TokenVerificationError(
                "Auth is not configured: set CLERK_ISSUER or CLERK_JWKS_URL "
                "(or AUTH_MODE=disabled for local single-user mode)"
            )
        parties = [
            p.strip()
            for p in settings.CLERK_AUTHORIZED_PARTIES.split(",")
            if p.strip()
        ]
        _token_verifier = ClerkJWKSVerifier(
            jwks_url=jwks_url,
            issuer=settings.CLERK_ISSUER,
            authorized_parties=parties,
        )
    return _token_verifier


def _fetch_email_from_clerk(clerk_id: str) -> Optional[str]:
    """Best-effort email lookup via the Clerk Backend API (needs secret key)."""
    if not settings.CLERK_SECRET_KEY:
        return None
    try:
        import httpx

        resp = httpx.get(
            f"{CLERK_API_BASE}/users/{clerk_id}",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        primary_id = data.get("primary_email_address_id")
        for entry in data.get("email_addresses", []):
            if entry.get("id") == primary_id:
                return entry.get("email_address")
        return None
    except Exception as exc:  # network/API failure must not block login
        logger.warning("Clerk email lookup failed for %s: %s", clerk_id, exc)
        return None


def provision_user(session, clerk_id: str, email: Optional[str]) -> User:
    """Fetch-or-create the users row for a verified clerk_id (JIT).

    Safe under concurrent first requests: unique violation on clerk_id is
    caught and resolved by re-reading.
    """
    from sqlalchemy.exc import IntegrityError

    user = session.query(User).filter(User.clerk_id == clerk_id).first()
    if user:
        if email and user.email != email:
            user.email = email
            session.commit()
        return user

    if email is None:
        email = _fetch_email_from_clerk(clerk_id)
    user = User(clerk_id=clerk_id, email=email)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        user = session.query(User).filter(User.clerk_id == clerk_id).first()
        if user is None:  # pragma: no cover - only on genuine DB failure
            raise
    return user


def resolve_identity(
    authorization: Optional[str],
    session_factory: Optional[Callable] = None,
) -> Optional[Identity]:
    """Turn an Authorization header into an Identity.

    Returns None for anonymous (no header). Raises TokenVerificationError for
    a present-but-invalid token — callers translate that to 401.
    """
    if settings.AUTH_MODE == "disabled":
        # Explicit local single-user mode: everything runs as admin.
        return Identity(
            user_id="local-dev", clerk_id="local-dev", email=None, role=ROLE_ADMIN
        )

    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TokenVerificationError("Expected 'Bearer <token>' Authorization header")

    claims = get_token_verifier().verify(token.strip())
    clerk_id = claims.get("sub")
    if not clerk_id:
        raise TokenVerificationError("Token has no sub claim")

    if session_factory is None:
        from app.core.database import SessionLocal

        session_factory = SessionLocal
    session = session_factory()
    try:
        user = provision_user(session, clerk_id, claims.get("email"))
        return Identity(
            user_id=str(user.id),
            clerk_id=user.clerk_id,
            email=user.email,
            role=user.role,
        )
    finally:
        session.close()


# --- FastAPI dependencies (REST) -------------------------------------------

def get_identity(request: Request) -> Optional[Identity]:
    try:
        return resolve_identity(request.headers.get("authorization"))
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_user(identity: Optional[Identity] = Depends(get_identity)) -> Identity:
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def require_admin(identity: Identity = Depends(require_user)) -> Identity:
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return identity
