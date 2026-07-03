from pathlib import Path
from typing import Optional

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


def find_env_file():
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return str(cwd_env)
    return str(PROJECT_ROOT / ".env")


settings = Settings(_env_file=find_env_file())
