"""SettingsManager against the setting registry: what an update may change,
and that a bad file or an unwritable path never raises (no DB, no torch)."""
import json
import logging

from app.core.settings_manager import SettingsManager
from app.core.settings_registry import SETTING_REGISTRY

FLOAT_DEF = next(d for d in SETTING_REGISTRY.values() if d.value_type is float)
STR_DEF = next(d for d in SETTING_REGISTRY.values() if d.value_type is str)


def manager(tmp_path, items):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(items), encoding="utf-8")
    return SettingsManager(config_path=str(cfg)), cfg


def test_unreadable_settings_file_falls_back_to_no_settings(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text("{not json", encoding="utf-8")
    sm = SettingsManager(config_path=str(cfg))
    assert sm.get_all_settings() == []
    assert sm.get_setting(FLOAT_DEF.key) == FLOAT_DEF.default      # registry default
    assert sm.get_setting("no_such_setting") == 0.0


def test_all_settings_are_listed_in_file_order(tmp_path):
    sm, _ = manager(tmp_path, [{"key": STR_DEF.key, "value": "a", "category": STR_DEF.category},
                               {"key": FLOAT_DEF.key, "value": 0.4}])
    assert [(s.key, s.value) for s in sm.get_all_settings()] == [(STR_DEF.key, "a"),
                                                                 (FLOAT_DEF.key, 0.4)]


def test_file_values_off_schema_are_loaded_but_reported(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        sm, _ = manager(tmp_path, [
            {"key": FLOAT_DEF.key, "value": "high", "category": "Somewhere else"},
            {"key": "retired_setting", "value": 1},
        ])
    text = caplog.text
    assert f"Setting '{FLOAT_DEF.key}' has type str, expected float" in text
    assert "has category 'Somewhere else'" in text
    assert "Unknown analysis setting key 'retired_setting'" in text
    assert sm.get_setting(FLOAT_DEF.key) == "high" and sm.get_setting("retired_setting") == 1


def test_update_refuses_unknown_keys_and_wrong_types(tmp_path, caplog):
    sm, cfg = manager(tmp_path, [{"key": FLOAT_DEF.key, "value": 0.4},
                                 {"key": STR_DEF.key, "value": "a"},
                                 {"key": "retired_setting", "value": 1}])
    before = cfg.read_text(encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert sm.update_setting("retired_setting", 2) is None      # not in the registry
        assert sm.update_setting(FLOAT_DEF.key, "0.9") is None
        assert sm.update_setting(FLOAT_DEF.key, True) is None       # a bool is not a number
        assert sm.update_setting(STR_DEF.key, 3) is None
    assert "Refusing to update unknown analysis setting 'retired_setting'" in caplog.text
    assert f"Refusing to update setting '{FLOAT_DEF.key}' with type str" in caplog.text
    assert sm.get_setting(FLOAT_DEF.key) == 0.4 and sm.get_setting(STR_DEF.key) == "a"
    assert cfg.read_text(encoding="utf-8") == before                # nothing was written


def test_whole_number_for_a_float_setting_is_stored_as_float(tmp_path):
    sm, cfg = manager(tmp_path, [{"key": FLOAT_DEF.key, "value": 0.4}])
    updated = sm.update_setting(FLOAT_DEF.key, 1)
    assert updated.value == 1.0 and isinstance(updated.value, float)
    stored = json.loads(cfg.read_text(encoding="utf-8"))
    assert stored[0]["key"] == FLOAT_DEF.key and stored[0]["value"] == 1.0


def test_registry_setting_missing_from_the_file_cannot_be_updated(tmp_path):
    sm, cfg = manager(tmp_path, [{"key": STR_DEF.key, "value": "a"}])
    assert sm.update_setting(FLOAT_DEF.key, 0.7) is None
    assert sm.get_setting(FLOAT_DEF.key) == FLOAT_DEF.default
    assert FLOAT_DEF.key not in cfg.read_text(encoding="utf-8")


def test_unwritable_settings_path_keeps_the_value_in_memory(tmp_path):
    sm, cfg = manager(tmp_path, [{"key": STR_DEF.key, "value": "a"}])
    sm.config_path = str(cfg / "below-a-file" / "settings.json")    # cannot be created
    assert sm.update_setting(STR_DEF.key, "b").value == "b"         # logged, not raised
    assert sm.get_setting(STR_DEF.key) == "b"
    assert json.loads(cfg.read_text(encoding="utf-8"))[0]["value"] == "a"
