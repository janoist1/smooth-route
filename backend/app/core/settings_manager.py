import json
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Setting(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    example: Optional[str] = None
    category: Optional[str] = None
    explanation: Optional[str] = None

class SettingsManager:
    """Manages analysis settings using a JSON file."""
    
    def __init__(self, config_path: str = "config/analysis_settings.json"):
        # Resolve absolute path
        if not os.path.isabs(config_path):
            # Assuming we are in backend/app/core, go up to backend/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.config_path = os.path.join(base_dir, config_path)
        else:
            self.config_path = config_path
            
        self._settings: Dict[str, Setting] = {}
        self._load_settings()

    def _load_settings(self):
        """Load settings from JSON file."""
        if not os.path.exists(self.config_path):
            print(f"Settings file not found at {self.config_path}, using empty defaults.")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    self._settings[item['key']] = Setting(**item)
        except Exception as e:
            print(f"Error loading settings: {e}")
            # Fallback to defaults or empty
            self._settings = {}

    def _save_settings(self):
        """Save settings to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = [s.model_dump() for s in self._settings.values()] # Use model_dump for Pydantic v2
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_setting(self, key: str, default: Any = 0.0) -> Any:
        """Get a setting value by key."""
        if key in self._settings:
            return self._settings[key].value
        return default

    def get_all_settings(self) -> List[Setting]:
        """Get all settings as a list."""
        return list(self._settings.values())

    def update_setting(self, key: str, value: Any) -> Optional[Setting]:
        """Update a setting value and save to file."""
        if key in self._settings:
            self._settings[key].value = value
            self._save_settings()
            return self._settings[key]
        return None

# Singleton instance
settings_manager = SettingsManager()
