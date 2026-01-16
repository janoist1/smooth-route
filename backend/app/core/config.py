from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
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

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def resolve_data_dir(self) -> str:
        """
        Resolves the absolute path to the data directory.
        Handles checking 'backend/data' vs 'data' relative to project root.
        """
        import os
        
        if os.path.isabs(self.DATA_DIR):
            return self.DATA_DIR
            
        # Determine anchor paths based on this file's location
        # this file: backend/app/core/config.py
        this_file = os.path.abspath(__file__)
        core_dir = os.path.dirname(this_file)
        app_dir = os.path.dirname(core_dir)
        backend_dir = os.path.dirname(app_dir)
        project_root = os.path.dirname(backend_dir)
        
        # Check candidates in priority order
        # 1. backend/data (explicitly inside backend module)
        backend_data = os.path.join(backend_dir, self.DATA_DIR)
        if os.path.exists(backend_data):
            return backend_data
            
        # 2. root/data (project root)
        root_data = os.path.join(project_root, self.DATA_DIR)
        if os.path.exists(root_data):
            return root_data
            
        # 3. Fallback: default to backend/data for creation
        return backend_data

def find_env_file():
    import os
    # content of current directory
    if os.path.exists(".env"):
        return ".env"
    # content of parent directory
    if os.path.exists(os.path.join("..", ".env")):
        return os.path.join("..", ".env")
    return ".env"

settings = Settings(_env_file=find_env_file())
