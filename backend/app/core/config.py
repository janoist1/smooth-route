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
