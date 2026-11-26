"""Unit tests for the pure damage%→RQI mapping (no torch, no DB).

Expectations in severity (sv(1) = best level), valid for either numbering.
"""
from app.core.rqi_scale import SCALE
from app.services.rqi_scoring import rqi_from_damage_percent

sv = SCALE.from_severity


def test_rqi_bands():
    assert rqi_from_damage_percent(0.0) == sv(1)
    assert rqi_from_damage_percent(0.49) == sv(1)
    assert rqi_from_damage_percent(0.5) == sv(2)
    assert rqi_from_damage_percent(1.9) == sv(2)
    assert rqi_from_damage_percent(2.0) == sv(3)
    assert rqi_from_damage_percent(4.9) == sv(3)
    assert rqi_from_damage_percent(5.0) == sv(4)
    assert rqi_from_damage_percent(9.9) == sv(4)
    assert rqi_from_damage_percent(10.0) == sv(5)
    assert rqi_from_damage_percent(100.0) == sv(5)


def test_rqi_gets_worse_with_more_damage():
    severities = [SCALE.to_severity(rqi_from_damage_percent(p)) for p in range(0, 20)]
    assert severities == sorted(severities)
