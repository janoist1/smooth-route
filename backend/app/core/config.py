from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Kátyúőr"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5433/smooth_route"
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    # Route alternatives: "Legsimább" = best length-weighted quality among the
    # routes at most this much slower than the fastest (0.2 = +20 %), and only
    # if at least this share of the route has quality data.
    ROUTE_SMOOTH_MAX_EXTRA_DURATION: float = 0.2
    ROUTE_SMOOTH_MIN_COVERAGE: float = 0.5

    # Auth (Clerk). AUTH_MODE:
    #   "clerk"    — verify Bearer JWTs against the Clerk JWKS (default, prod-safe)
    #   "disabled" — single-user local mode: every request acts as admin.
    #                Explicit opt-out for development without a Clerk instance.
    AUTH_MODE: str = "clerk"
    CLERK_SECRET_KEY: Optional[str] = None
    # Issuer URL of the Clerk instance, e.g. https://xxx.clerk.accounts.dev
    CLERK_ISSUER: Optional[str] = None
    # Explicit JWKS URL; defaults to {CLERK_ISSUER}/.well-known/jwks.json
    CLERK_JWKS_URL: Optional[str] = None
    # Comma-separated list of origins accepted in the token's azp claim.
    CLERK_AUTHORIZED_PARTIES: str = "http://localhost:5173"

    # Run Alembic migrations at app startup (disable when migrating explicitly).
    RUN_MIGRATIONS_ON_STARTUP: bool = True

    # Public read-only deploy (round 1): serve only the read GraphQL schema (no
    # mutations), skip the local-only pieces, and let route planning stay
    # anonymous. Local dev keeps this False → full app unchanged.
    PUBLIC_READ_ONLY: bool = False
    # Comma-separated CORS origins used when PUBLIC_READ_ONLY (prod frontend).
    ALLOWED_ORIGINS: str = "https://simaut.hu"

    # Quota limits
    DAILY_IMAGE_QUOTA: int = 1000  # Conservative default
    # Combined Directions + Geocoding requests per Pacific calendar day.
    # Zero disables billable route calls; negative values are invalid.
    GOOGLE_DIRECTIONS_DAILY_CAP: int = Field(default=300, ge=0)
    # Optional counter file override. Public default is ephemeral /tmp;
    # local default is DATA_DIR/quota/google_directions.json.
    GOOGLE_DIRECTIONS_QUOTA_PATH: Optional[str] = None

    # Deduplication settings
    DEDUPLICATION_RADIUS_METERS: float = 10.0
    DEDUPLICATION_HEADING_TOLERANCE: float = 30.0

    # Data directory for storing images
    DATA_DIR: str = "data"  # Relative to project root or absolute path

    def resolve_data_dir(self) -> str:
        """Resolve DATA_DIR once, relative to the repository root."""
        configured = Path(self.DATA_DIR).expanduser()
        if configured.is_absolute():
            return str(configured.resolve())
        return str((PROJECT_ROOT / configured).resolve())

    def check_public_auth(self) -> None:
        """Refuse to start the public read-only deploy with auth disabled.

        AUTH_MODE=disabled makes every caller an admin, so on the public
        site it would expose the admin fields to anonymous visitors.
        """
        if self.PUBLIC_READ_ONLY and self.AUTH_MODE.strip().lower() == "disabled":
            raise RuntimeError(
                "PUBLIC_READ_ONLY=1 cannot run with AUTH_MODE=disabled "
                "(every caller would be admin); unset AUTH_MODE or use 'clerk'."
            )


def find_env_file():
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return str(cwd_env)
    return str(PROJECT_ROOT / ".env")


settings = Settings(_env_file=find_env_file())  # pyright: ignore[reportCallIssue]  (pydantic-settings init kwarg)
