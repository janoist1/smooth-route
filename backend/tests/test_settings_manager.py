"""Isolated unit tests for SettingsManager (no DB, no torch)."""

import json
import logging
from pathlib import Path

from app.core.settings_registry import SETTING_REGISTRY
from app.core.settings_manager import SettingsManager


def _write(tmp_path, items):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(items), encoding="utf-8")
    return str(cfg)


def test_get_setting_returns_value_and_default(tmp_path):
    path = _write(
        tmp_path,
        [
            {"key": "rqi_display_source", "value": "dino"},
            {"key": "threshold", "value": 42},
        ],
    )
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


def test_registered_missing_setting_uses_schema_default(tmp_path):
    sm = SettingsManager(config_path=_write(tmp_path, []))

    assert sm.get_setting("google_maps_pitch") == -20


def test_unknown_key_logs_warning_but_remains_readable(tmp_path, caplog):
    caplog.set_level(logging.WARNING)

    sm = SettingsManager(
        config_path=_write(tmp_path, [{"key": "legacy_weight", "value": 0.5}])
    )

    assert sm.get_setting("legacy_weight") == 0.5
    assert "Unknown analysis setting key 'legacy_weight'" in caplog.text


def test_live_json_matches_registry():
    config_path = (
        Path(__file__).resolve().parents[1] / "config" / "analysis_settings.json"
    )
    items = json.loads(config_path.read_text(encoding="utf-8"))

    assert {item["key"] for item in items} == set(SETTING_REGISTRY)


def test_float_setting_accepts_integer_json_number(tmp_path):
    path = _write(
        tmp_path,
        [{"key": "yolo_inference_conf", "value": 0.25}],
    )
    sm = SettingsManager(config_path=path)

    updated = sm.update_setting("yolo_inference_conf", 1)

    assert updated is not None
    assert updated.value == 1.0
