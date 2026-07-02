"""Unit tests for the pure damage%→RQI mapping (no torch, no DB)."""
from app.services.rqi_scoring import rqi_from_damage_percent


def test_rqi_bands():
    assert rqi_from_damage_percent(0.0) == 1.0
    assert rqi_from_damage_percent(0.49) == 1.0
    assert rqi_from_damage_percent(0.5) == 2.0
    assert rqi_from_damage_percent(1.9) == 2.0
    assert rqi_from_damage_percent(2.0) == 3.0
    assert rqi_from_damage_percent(4.9) == 3.0
    assert rqi_from_damage_percent(5.0) == 4.0
    assert rqi_from_damage_percent(9.9) == 4.0
    assert rqi_from_damage_percent(10.0) == 5.0
    assert rqi_from_damage_percent(100.0) == 5.0


def test_rqi_is_monotonic_non_decreasing():
    scores = [rqi_from_damage_percent(p) for p in range(0, 20)]
    assert scores == sorted(scores)
