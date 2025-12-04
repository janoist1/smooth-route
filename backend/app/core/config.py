from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Kátyúőr"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/smooth_route"
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    
    # Quota limits
    DAILY_IMAGE_QUOTA: int = 1000  # Conservative default

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
