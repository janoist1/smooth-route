"""Pin the canonical RQI scale (shared/rqi_scale.json) and its helpers.

No torch, no DB. The flipped-scale tests prove the helpers are direction-
agnostic. A direction flip must leave every bucket count / bad-road decision
the same once the stored values are mirrored (x -> 6 - x).
"""
import copy
import json
import os

import pytest

from app.core.rqi_scale import (HIGHER_IS_BETTER, LOWER_IS_BETTER, SCALE,
                                SCALE_PATH, RqiScale)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED = os.path.join(REPO_ROOT, "shared", "rqi_scale.json")


def flipped_scale() -> RqiScale:
    """The same scale with the numbers mirrored (5 = best), as phase 2 would ship it."""
    return SCALE.mirrored()


# ----- the definition itself ----------------------------------------------

def test_backend_copy_matches_shared_source():
    if not os.path.exists(SHARED):  # deployed backend/ without the repo root
        pytest.skip("shared/rqi_scale.json not present")
    with open(SHARED, "rb") as a, open(SCALE_PATH, "rb") as b:
        assert a.read() == b.read(), "run: python scripts/sync_rqi_scale.py"


def test_five_levels_with_hungarian_labels():
    assert SCALE.values == (1, 2, 3, 4, 5)
    assert [lv.key for lv in SCALE.levels] == ["excellent", "good", "fair", "poor", "very_poor"]
    assert [lv.label_hu for lv in SCALE.levels] == ["Kiváló", "Jó", "Közepes", "Rossz", "Nagyon rossz"]
    assert [lv.label_en for lv in SCALE.levels] == ["Excellent", "Good", "Fair", "Poor", "Very poor"]
    for lv in SCALE.levels:
        assert lv.rubric_hu and lv.rubric_en and lv.color.startswith("#")


def test_current_direction_and_model_contract():
    # Phase 1 keeps today's numbering: 1 = Kiváló (best). The flip is phase 2.
    assert SCALE.direction == LOWER_IS_BETTER
    assert SCALE.best == 1 and SCALE.worst == 5
    assert SCALE.model_levels == (1, 2, 3, 4)       # 5 has 14 labels, not trained
    assert SCALE.bad_from == SCALE.value_of("fair") == 3
    assert SCALE.severity_values(SCALE.model_levels) == [1, 2, 3, 4]


def test_middle_level_is_its_own_mirror():
    # Közepes sits in the middle, so bad_from survives a flip numerically.
    assert SCALE.flip(SCALE.value_of("fair")) == SCALE.value_of("fair")


def test_invalid_scale_rejected():
    bad = copy.deepcopy(SCALE.data)
    bad["direction"] = "up"
    with pytest.raises(ValueError):
        RqiScale(bad)
    bad = copy.deepcopy(SCALE.data)
    bad["bad_from"] = 9
    with pytest.raises(ValueError):
        RqiScale(bad)
    bad = copy.deepcopy(SCALE.data)
    del bad["levels"][2]
    with pytest.raises(ValueError):
        RqiScale(bad)


# ----- helpers -------------------------------------------------------------

def test_ordering_helpers():
    assert SCALE.at_or_better(2, 2) and SCALE.at_or_better(1, 2)
    assert SCALE.worse_than(3, 2) and not SCALE.worse_than(2, 2)
    assert SCALE.is_bad(3) and SCALE.is_bad(4) and not SCALE.is_bad(2)
    assert sorted([1, 4, 2, 3], key=SCALE.worst_first_key) == [4, 3, 2, 1]


def test_rounding_matches_legacy_call_sites():
    # nearest(ties=better) == frontend getRQILabel bands (<=1.5 -> 1 ...)
    assert [SCALE.nearest(x) for x in (0.2, 1.5, 1.51, 2.5, 3.5, 4.5, 4.6, 9)] == [1, 1, 2, 2, 3, 4, 5, 5]
    # nearest(ties=worse) == trainingStats rqiNCount bins (1.5 <= s < 2.5 -> 2)
    assert [SCALE.nearest(x, "worse") for x in (1.49, 1.5, 2.5, 3.5, 4.5)] == [1, 2, 3, 4, 5]
    # toward_worse == frontend getRQIColor bands (2.0 green, 2.01 yellow)
    assert [SCALE.toward_worse(x) for x in (0, 2.0, 2.01, 3.0, 4.0, 4.01, 7)] == [1, 2, 3, 3, 4, 5, 5]
    assert SCALE.midpoint("fair", "poor") == 3.5


def test_labels():
    assert SCALE.label(1) == "Kiváló"
    assert SCALE.label(2.6) == "Közepes"
    assert SCALE.label(4.8, "en") == "Very poor"
    assert SCALE.label(None) == "Nincs adat"


def test_severity_round_trip_is_identity_today():
    for x in (1, 1.5, 2.48, 4, 5):
        assert SCALE.to_severity(x) == x
        assert SCALE.from_severity(SCALE.to_severity(x)) == x


def test_helpers_work_on_sqlalchemy_columns():
    sa = pytest.importorskip("sqlalchemy")
    col = sa.column("dino_rqi_score")
    expr = SCALE.at_or_better(col, SCALE.value_of("good"))
    assert str(expr.compile(compile_kwargs={"literal_binds": True})) == "dino_rqi_score <= 2"


# ----- a flipped scale gives the same answers on mirrored data -------------

def test_flipped_scale_is_consistent():
    F = flipped_scale()
    assert F.direction == HIGHER_IS_BETTER
    assert F.best == 5 and F.worst == 1
    assert [lv.label_hu for lv in F.levels] == ["Kiváló", "Jó", "Közepes", "Rossz", "Nagyon rossz"]
    assert F.model_levels == (5, 4, 3, 2)
    assert F.severity_values(F.model_levels) == [1, 2, 3, 4]
    assert F.bad_from == 3


@pytest.mark.parametrize("x", [0.7, 1.0, 1.5, 1.51, 2.0, 2.01, 2.5, 3.0, 3.18, 3.5, 4.0, 4.5, 5.0, 6.2])
def test_flip_preserves_every_decision(x):
    F = flipped_scale()
    y = 6 - x  # the value after the phase-2 data migration
    assert F.is_bad(y) == SCALE.is_bad(x)
    assert F.nearest(y) == 6 - SCALE.nearest(x)
    assert F.nearest(y, "worse") == 6 - SCALE.nearest(x, "worse")
    assert F.toward_worse(y) == 6 - SCALE.toward_worse(x)
    assert F.label(y) == SCALE.label(x)
    assert F.to_severity(y) == pytest.approx(x)
    assert F.at_or_better(y, F.value_of("good")) == SCALE.at_or_better(x, SCALE.value_of("good"))
    assert F.worse_than(y, F.midpoint("fair", "poor")) == SCALE.worse_than(x, SCALE.midpoint("fair", "poor"))


def test_shared_json_is_valid_json_with_comment():
    with open(SCALE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert "shared/rqi_scale.json" in data["$comment"]


# ----- the ML view (ml/rqi_scale.py) is pinned here because CI runs pytest --

def _load_ml_view():
    import importlib.util
    path = os.path.join(REPO_ROOT, "ml", "rqi_scale.py")
    if not os.path.exists(path):
        pytest.skip("ml/ not present")
    spec = importlib.util.spec_from_file_location("ml_rqi_scale_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ml_view_constants_are_todays_numbers():
    R = _load_ml_view()
    assert R.LEVELS == [1, 2, 3, 4, 5]
    assert R.MODEL_LEVELS == [1, 2, 3, 4]
    assert R.DROPPED_LEVELS == [5]
    assert R.BAD_FROM == 3
    assert (R.MODEL_MIN, R.MODEL_MAX) == (1, 4)
    assert R.SCALE_DIRECTION == LOWER_IS_BETTER
    assert R.sql_to_severity("manual_rqi") == "manual_rqi"


def test_ml_view_after_a_flip_keeps_severity_numbers():
    R = _load_ml_view()
    F = R.RqiScale(R.SCALE.mirrored_data())
    # ML constants are severity numbers: a canonical flip must not move them.
    assert F.severity_values(F.model_levels) == R.MODEL_LEVELS
    assert int(F.to_severity(F.bad_from)) == R.BAD_FROM
    # ...and the export would convert stored canonical values back to severity.
    assert F.to_severity(5) == 1 and F.to_severity(4.5) == 1.5
