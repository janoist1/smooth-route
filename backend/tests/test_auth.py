"""Unit tests for Clerk JWT verification, JIT provisioning and REST guards."""
import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import auth
from app.core.auth import (
    ClerkJWKSVerifier,
    Identity,
    TokenVerificationError,
    provision_user,
    require_admin,
    require_user,
    resolve_identity,
)
from app.core.config import settings
from app.models.models import User

ISSUER = "https://test-instance.clerk.accounts.dev"
PARTY = "http://localhost:5173"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(rsa_key):
    v = ClerkJWKSVerifier(
        jwks_url="http://unused.local/jwks.json",
        issuer=ISSUER,
        authorized_parties=[PARTY],
    )
    public_pem = rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Bypass the network JWKS fetch; signature checking stays real.
    v._jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_pem)
    )
    return v


def make_token(rsa_key, **overrides):
    now = int(time.time())
    claims = {
        "sub": "user_abc123",
        "iss": ISSUER,
        "azp": PARTY,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return pyjwt.encode(claims, rsa_key, algorithm="RS256")


class TestClerkJWKSVerifier:
    def test_valid_token_returns_claims(self, verifier, rsa_key):
        claims = verifier.verify(make_token(rsa_key))
        assert claims["sub"] == "user_abc123"

    def test_expired_token_rejected(self, verifier, rsa_key):
        token = make_token(rsa_key, exp=int(time.time()) - 100)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_wrong_issuer_rejected(self, verifier, rsa_key):
        token = make_token(rsa_key, iss="https://evil.example.com")
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_unauthorized_party_rejected(self, verifier, rsa_key):
        token = make_token(rsa_key, azp="https://evil.example.com")
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_missing_sub_rejected(self, verifier, rsa_key):
        token = make_token(rsa_key, sub=None)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_garbage_token_rejected(self, verifier):
        verifier._jwk_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda token: (_ for _ in ()).throw(
                pyjwt.DecodeError("not a jwt")
            )
        )
        with pytest.raises(TokenVerificationError):
            verifier.verify("garbage")


class TestResolveIdentity:
    def test_disabled_mode_returns_local_admin(self, monkeypatch):
        monkeypatch.setattr(settings, "AUTH_MODE", "disabled")
        identity = resolve_identity(None)
        assert identity is not None and identity.is_admin

    def test_anonymous_when_no_header(self, clerk_mode):
        assert resolve_identity(None) is None

    def test_non_bearer_scheme_rejected(self, clerk_mode):
        with pytest.raises(TokenVerificationError):
            resolve_identity("Basic dXNlcjpwdw==")

    def test_unconfigured_clerk_rejects_tokens(self, clerk_mode, monkeypatch):
        monkeypatch.setattr(settings, "CLERK_ISSUER", None)
        monkeypatch.setattr(settings, "CLERK_JWKS_URL", None)
        auth.set_token_verifier(None)
        with pytest.raises(TokenVerificationError, match="not configured"):
            resolve_identity("Bearer some.token.here")

    def test_valid_token_provisions_user_jit(
        self, clerk_mode, fake_verifier, users_session_factory
    ):
        fake_verifier.claims_by_token["tok1"] = {"sub": "user_jit", "email": "a@b.hu"}

        identity = resolve_identity("Bearer tok1", session_factory=users_session_factory)

        assert identity is not None
        assert identity.clerk_id == "user_jit"
        assert identity.email == "a@b.hu"
        assert identity.role == "user"
        assert not identity.is_admin

        # Second request reuses the row instead of duplicating it.
        again = resolve_identity("Bearer tok1", session_factory=users_session_factory)
        assert again is not None and again.user_id == identity.user_id
        with users_session_factory() as s:
            assert s.query(User).count() == 1

    def test_invalid_token_raises(self, clerk_mode, fake_verifier, users_session_factory):
        with pytest.raises(TokenVerificationError):
            resolve_identity("Bearer unknown", session_factory=users_session_factory)

    def test_admin_role_read_from_db(self, clerk_mode, fake_verifier, users_session_factory):
        fake_verifier.claims_by_token["tok2"] = {"sub": "user_admin"}
        with users_session_factory() as s:
            s.add(User(clerk_id="user_admin", email=None, role="admin"))
            s.commit()

        identity = resolve_identity("Bearer tok2", session_factory=users_session_factory)
        assert identity is not None and identity.is_admin


class TestProvisionUser:
    def test_updates_changed_email(self, users_session_factory):
        with users_session_factory() as s:
            provision_user(s, "user_x", "old@x.hu")
        with users_session_factory() as s:
            user = provision_user(s, "user_x", "new@x.hu")
            assert user.email == "new@x.hu"


def _rest_app():
    """Probe app: real dependencies, no real handlers (no DB side effects)."""
    app = FastAPI()

    @app.get("/probe-user")
    def probe_user(identity: Identity = Depends(require_user)):
        return {"role": identity.role}

    @app.get("/probe-admin")
    def probe_admin(identity: Identity = Depends(require_admin)):
        return {"role": identity.role}

    return app


class TestRestGuards:
    def test_missing_token_is_401(self, clerk_mode):
        client = TestClient(_rest_app())
        resp = client.get("/probe-user")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == "Bearer"

    def test_invalid_token_is_401(self, clerk_mode, fake_verifier):
        client = TestClient(_rest_app())
        resp = client.get("/probe-user", headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401

    def test_user_token_is_403_on_admin_route(
        self, clerk_mode, fake_verifier, users_session_factory, monkeypatch
    ):
        import app.core.database as database

        monkeypatch.setattr(database, "SessionLocal", users_session_factory)
        fake_verifier.claims_by_token["tok"] = {"sub": "user_plain"}

        client = TestClient(_rest_app())
        resp = client.get("/probe-admin", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 403

    def test_user_token_passes_user_route(
        self, clerk_mode, fake_verifier, users_session_factory, monkeypatch
    ):
        import app.core.database as database

        monkeypatch.setattr(database, "SessionLocal", users_session_factory)
        fake_verifier.claims_by_token["tok"] = {"sub": "user_plain"}

        client = TestClient(_rest_app())
        resp = client.get("/probe-user", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 200
        assert resp.json() == {"role": "user"}

    def test_protected_api_routes_reject_anonymous(self, clerk_mode):
        """The real router's mutating endpoints 401 before touching handlers."""
        from app.api.routes import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/process-route",
            json={
                "origin_lat": 47.5,
                "origin_lng": 19.0,
                "destination_lat": 47.6,
                "destination_lng": 19.1,
            },
        )
        assert resp.status_code == 401

        resp = client.post("/api/v1/job/whatever/stop")
        assert resp.status_code == 401
