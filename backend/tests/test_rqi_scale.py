"""Pin the canonical RQI scale (shared/rqi_scale.json) and its helpers.

No torch, no DB. Expectations are written in SEVERITY terms (sv(k) = level k
counted from the best, 1 = Kiváló), so they hold for either numbering. After a
direction flip (`scripts/sync_rqi_scale.py --flip`), the ONLY test meant to fail
is test_current_direction_pin. It pins today's numbers and is updated on purpose.
"""
import copy
import json
import os

import pytest

from app.core.rqi_scale import (HIGHER_IS_BETTER, LOWER_IS_BETTER, SCALE,
                                SCALE_PATH, SEVERITY, RqiScale)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED = os.path.join(REPO_ROOT, "shared", "rqi_scale.json")

sv = SCALE.from_severity  # severity number (1 = best) -> canonical value


# ----- the definition itself ----------------------------------------------

def test_backend_copy_matches_shared_source():
    if not os.path.exists(SHARED):  # deployed backend/ without the repo root
        pytest.skip("shared/rqi_scale.json not present")
    with open(SHARED, "rb") as a, open(SCALE_PATH, "rb") as b:
        assert a.read() == b.read(), "run: python scripts/sync_rqi_scale.py"


def test_current_direction_pin():
    # THE direction pin. Owner's decision 2026-11-26 ("5 kiváló mehet"):
    # 5 = Kiváló (best) ... 1 = Nagyon rossz; new = 6 - old. Stored data is
    # converted by alembic rqi_flip_direction. A deliberate flip changes exactly these lines.
    assert SCALE.direction == HIGHER_IS_BETTER
    assert SCALE.best == 5 and SCALE.worst == 1
    assert SCALE.model_levels == (5, 4, 3, 2)
    assert SCALE.bad_from == 3  # bad road = Közepes or worse = value <= 3
    assert [SCALE.to_severity(x) for x in (5, 4.5, 3.52, 2, 1)] == [1, 1.5, 2.48, 4, 5]


def test_five_distinct_colours_good_to_bad():
    colours = [lv.color.lower() for lv in SCALE.levels]
    assert colours == ["#1f5fa8", "#3d9ad6", "#e0a400", "#e8632b", "#b3172c"]
    assert len(set(colours)) == 5 and SCALE.unknown_color.lower() not in colours


def test_five_levels_with_hungarian_labels_best_first():
    assert sorted(SCALE.values) == [1, 2, 3, 4, 5]
    assert [lv.key for lv in SCALE.levels] == ["excellent", "good", "fair", "poor", "very_poor"]
    assert [lv.label_hu for lv in SCALE.levels] == ["Kiváló", "Jó", "Közepes", "Rossz", "Nagyon rossz"]
    assert [lv.label_en for lv in SCALE.levels] == ["Excellent", "Good", "Fair", "Poor", "Very poor"]
    assert [SCALE.to_severity(v) for v in SCALE.values] == [1, 2, 3, 4, 5]
    for lv in SCALE.levels:
        assert lv.rubric_hu and lv.rubric_en and lv.color.startswith("#")


def test_labelling_rule_is_part_of_the_definition():
    # Owner decision 2026-11-26: the label rates the visible surface only;
    # speed limit / road class are deliberately NOT part of it.
    assert "sebességkorlát" in SCALE.data["rubric_note_hu"]
    assert "speed limit" in SCALE.data["rubric_note_en"]
    very_poor = SCALE.level(SCALE.value_of("very_poor"))
    assert "földút" in very_poor.rubric_hu and "gravel" in very_poor.rubric_en


def test_model_contract():
    # 5 / Nagyon rossz has 14 (mostly junk) labels: never trained, never predicted.
    assert SCALE.severity_values(SCALE.model_levels) == [1, 2, 3, 4]
    assert SCALE.worst not in SCALE.model_levels
    assert SCALE.bad_from == SCALE.value_of("fair")


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


def test_shared_json_carries_the_edit_rule():
    with open(SCALE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert "shared/rqi_scale.json" in data["$comment"]


# ----- helpers -------------------------------------------------------------

def test_ordering_helpers():
    assert SCALE.at_or_better(sv(2), sv(2)) and SCALE.at_or_better(sv(1), sv(2))
    assert SCALE.worse_than(sv(3), sv(2)) and not SCALE.worse_than(sv(2), sv(2))
    assert SCALE.better_than(sv(1), sv(2)) and SCALE.at_or_worse(sv(3), sv(3))
    assert SCALE.is_bad(sv(3)) and SCALE.is_bad(sv(4)) and not SCALE.is_bad(sv(2.9))
    assert sorted([sv(1), sv(4), sv(2), sv(3)], key=SCALE.worst_first_key) == [sv(4), sv(3), sv(2), sv(1)]


def test_rounding_matches_legacy_call_sites():
    # nearest(ties=better) == frontend getRQILabel bands (<= 1.5 -> 1 ...)
    assert ([SCALE.nearest(sv(x)) for x in (0.2, 1.5, 1.51, 2.5, 3.5, 4.5, 4.6, 9)]
            == [sv(k) for k in (1, 1, 2, 2, 3, 4, 5, 5)])
    # nearest(ties=worse) == trainingStats rqiNCount bins (1.5 <= s < 2.5 -> 2)
    assert ([SCALE.nearest(sv(x), "worse") for x in (1.49, 1.5, 2.5, 3.5, 4.5)]
            == [sv(k) for k in (1, 2, 3, 4, 5)])
    # toward_worse == frontend getRQIColor bands (2.0 green, 2.01 yellow)
    assert ([SCALE.toward_worse(sv(x)) for x in (0, 2.0, 2.01, 3.0, 4.0, 4.01, 7)]
            == [sv(k) for k in (1, 2, 3, 3, 4, 5, 5)])
    assert SCALE.midpoint("fair", "poor") == sv(3.5)


def test_labels():
    assert SCALE.label(sv(1)) == "Kiváló"
    assert SCALE.label(sv(2.6)) == "Közepes"
    assert SCALE.label(sv(4.8), "en") == "Very poor"
    assert SCALE.label(None) == "Nincs adat"


def test_severity_round_trip():
    for x in (1, 1.5, 2.48, 4, 5):
        assert SCALE.from_severity(SCALE.to_severity(x)) == pytest.approx(x)


def test_helpers_work_on_sqlalchemy_columns():
    sa = pytest.importorskip("sqlalchemy")
    col = sa.column("dino_rqi_score")
    expr = SCALE.at_or_better(col, SCALE.value_of("good"))
    op = "<=" if SCALE.lower_is_better else ">="
    assert (str(expr.compile(compile_kwargs={"literal_binds": True}))
            == f"dino_rqi_score {op} {SCALE.value_of('good')}")


# ----- the mirrored scale gives the same answers on mirrored data ----------

def test_mirrored_scale_is_consistent():
    F = SCALE.mirrored()
    assert {F.direction, SCALE.direction} == {LOWER_IS_BETTER, HIGHER_IS_BETTER}
    assert F.best == SCALE.flip(SCALE.best) and F.worst == SCALE.flip(SCALE.worst)
    assert [lv.label_hu for lv in F.levels] == [lv.label_hu for lv in SCALE.levels]
    assert F.model_levels == tuple(SCALE.flip(v) for v in SCALE.model_levels)
    assert F.severity_values(F.model_levels) == SCALE.severity_values(SCALE.model_levels)
    assert F.bad_from == SCALE.flip(SCALE.bad_from)
    assert F.mirrored_data() == SCALE.data  # flipping twice is the identity


@pytest.mark.parametrize("x", [0.7, 1.0, 1.5, 1.51, 2.0, 2.01, 2.5, 3.0, 3.18, 3.5, 4.0, 4.5, 5.0, 6.2])
def test_flip_preserves_every_decision(x):
    F = SCALE.mirrored()
    y = 6 - x  # the value after the phase-2 data migration
    assert F.is_bad(y) == SCALE.is_bad(x)
    assert F.nearest(y) == 6 - SCALE.nearest(x)
    assert F.nearest(y, "worse") == 6 - SCALE.nearest(x, "worse")
    assert F.toward_worse(y) == 6 - SCALE.toward_worse(x)
    assert F.label(y) == SCALE.label(x)
    assert F.to_severity(y) == pytest.approx(SCALE.to_severity(x))
    assert F.at_or_better(y, F.value_of("good")) == SCALE.at_or_better(x, SCALE.value_of("good"))
    assert (F.worse_than(y, F.midpoint("fair", "poor"))
            == SCALE.worse_than(x, SCALE.midpoint("fair", "poor")))


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


def test_ml_view_uses_severity_numbers_in_any_direction():
    R = _load_ml_view()
    assert R.LEVELS == [1, 2, 3, 4, 5]
    assert R.MODEL_LEVELS == [1, 2, 3, 4]
    assert R.DROPPED_LEVELS == [5]
    assert R.BAD_FROM == 3
    assert (R.MODEL_MIN, R.MODEL_MAX) == (1, 4)
    assert R.SCALE_DIRECTION == SEVERITY
    expected = "manual_rqi" if R.SCALE.direction == SEVERITY else "(6 - manual_rqi)"
    assert R.sql_to_severity("manual_rqi") == expected


def test_ml_severity_of_each_level_survives_a_flip():
    R = _load_ml_view()
    F = R.RqiScale(R.SCALE.mirrored_data())
    for lv in R.SCALE.levels:
        assert F.to_severity(F.value_of(lv.key)) == R.SCALE.to_severity(lv.value)
    assert F.severity_values(F.model_levels) == R.MODEL_LEVELS
    assert int(F.to_severity(F.bad_from)) == R.BAD_FROM


# ----- the segment layer's config must agree with the canonical scale -------

def test_segment_config_scale_matches_the_canonical_scale():
    """backend/config/segment_aggregation.json carries its own "scale" block
    (RqiScale in segment_aggregation). It must state exactly what
    shared/rqi_scale.json states, so the two can never drift apart."""
    from app.services.segment_aggregation import load_config
    seg = load_config().scale
    assert tuple(sorted(seg.classes)) == tuple(sorted(SCALE.model_levels))
    assert seg.higher_is_worse == SCALE.lower_is_better
    assert seg.bad_class == SCALE.bad_from
    assert seg.best_to_worst == SCALE.model_levels  # best first, both sides


def test_segment_thresholds_are_the_ml_recipe_in_canonical_numbering():
    """The ML recipe (ml/segment_recipe.json) is tuned in severity numbering;
    the backend config holds the same cut-points on the canonical scale."""
    from app.services.segment_aggregation import load_config
    recipe_path = os.path.join(REPO_ROOT, "ml", "segment_recipe.json")
    if not os.path.exists(recipe_path):
        pytest.skip("ml/ not present")
    with open(recipe_path, encoding="utf-8") as f:
        recipe = json.load(f)
    assert recipe.get("scale_direction", SEVERITY) == SEVERITY
    canonical = sorted(round(SCALE.to_severity(t), 3) for t in load_config().thresholds)
    assert canonical == pytest.approx(sorted(recipe["thresholds"]))
