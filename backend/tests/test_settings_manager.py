"""Isolated unit tests for SettingsManager (no DB, no torch)."""
import json

from app.core.settings_manager import SettingsManager


def _write(tmp_path, items):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(items), encoding="utf-8")
    return str(cfg)


def test_get_setting_returns_value_and_default(tmp_path):
    path = _write(tmp_path, [
        {"key": "rqi_display_source", "value": "dino"},
        {"key": "threshold", "value": 42},
    ])
    sm = SettingsManager(config_path=path)

    assert sm.get_setting("rqi_display_source") == "dino"
    assert sm.get_setting("threshold") == 42
    # unknown key -> provided default
    assert sm.get_setting("missing", "fallback") == "fallback"


def test_update_setting_persists_to_disk(tmp_path):
    path = _write(tmp_path, [{"key": "rqi_display_source", "value": "yolo"}])
    sm = SettingsManager(config_path=path)

    sm.update_setting("rqi_display_source", "dino")

    # A fresh manager reading the same file should see the update.
    reloaded = SettingsManager(config_path=path)
    assert reloaded.get_setting("rqi_display_source") == "dino"


def test_missing_file_falls_back_to_empty(tmp_path):
    sm = SettingsManager(config_path=str(tmp_path / "does_not_exist.json"))
    assert sm.get_setting("anything", "default") == "default"
