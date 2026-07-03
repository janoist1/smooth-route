import json
import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.settings_registry import SETTING_REGISTRY, SettingDefinition

logger = logging.getLogger(__name__)
_UNSET = object()


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
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            self.config_path = os.path.join(base_dir, config_path)
        else:
            self.config_path = config_path

        self._settings: Dict[str, Setting] = {}
        self._load_settings()

    def _load_settings(self):
        """Load settings from JSON file."""
        if not os.path.exists(self.config_path):
            print(
                f"Settings file not found at {self.config_path}, using empty defaults."
            )
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    key = item["key"]
                    definition = SETTING_REGISTRY.get(key)
                    if definition is None:
                        logger.warning(
                            "Unknown analysis setting key '%s' in %s",
                            key,
                            self.config_path,
                        )
                    else:
                        self._warn_schema_mismatch(item, definition)
                    self._settings[key] = Setting(**item)
        except Exception as e:
            print(f"Error loading settings: {e}")
            # Fallback to defaults or empty
            self._settings = {}

    def _save_settings(self):
        """Save settings to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = [
                s.model_dump() for s in self._settings.values()
            ]  # Use model_dump for Pydantic v2
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    @staticmethod
    def _value_matches_definition(value: Any, definition: SettingDefinition) -> bool:
        if definition.value_type is float:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return type(value) is definition.value_type

    @staticmethod
    def _warn_schema_mismatch(
        item: Dict[str, Any], definition: SettingDefinition
    ) -> None:
        value = item.get("value")
        if not SettingsManager._value_matches_definition(value, definition):
            logger.warning(
                "Setting '%s' has type %s, expected %s",
                definition.key,
                type(value).__name__,
                definition.value_type.__name__,
            )
        category = item.get("category")
        if category and category != definition.category:
            logger.warning(
                "Setting '%s' has category '%s', expected '%s'",
                definition.key,
                category,
                definition.category,
            )

    def get_setting(self, key: str, default: Any = _UNSET) -> Any:
        """Get a setting value by key."""
        if key in self._settings:
            return self._settings[key].value
        if default is not _UNSET:
            return default
        definition = SETTING_REGISTRY.get(key)
        return definition.default if definition else 0.0

    def get_all_settings(self) -> List[Setting]:
        """Get all settings as a list."""
        return list(self._settings.values())

    def update_setting(self, key: str, value: Any) -> Optional[Setting]:
        """Update a setting value and save to file."""
        definition = SETTING_REGISTRY.get(key)
        if definition is None:
            logger.warning("Refusing to update unknown analysis setting '%s'", key)
            return None
        if not self._value_matches_definition(value, definition):
            logger.warning(
                "Refusing to update setting '%s' with type %s; expected %s",
                key,
                type(value).__name__,
                definition.value_type.__name__,
            )
            return None
        if definition.value_type is float:
            value = float(value)
        if key in self._settings:
            self._settings[key].value = value
            self._save_settings()
            return self._settings[key]
        return None


# Singleton instance
settings_manager = SettingsManager()
