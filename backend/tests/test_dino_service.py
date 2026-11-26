"""Unit tests for DinoInferenceService decision logic (no torch model load).

dino_service imports torch/numpy/PIL at module level, so on torch-free
environments (CI) this module is skipped; it runs fully on the dev machine.
"""
import pytest

pytest.importorskip("torch")

from app.services.dino_service import (DinoInferenceService, EXPECTED_V2_KEYS,
                                       validate_artifact)


def make_service(thresholds=None):
    svc = DinoInferenceService.__new__(DinoInferenceService)
    svc.thresholds = thresholds
    svc.rqi_clip = (1, 4)
    return svc


def test_rqi_from_score_fallback_rounding():
    svc = make_service(thresholds=None)
    assert svc.rqi_from_score(0.4) == 1     # clipped low
    assert svc.rqi_from_score(1.4) == 1
    assert svc.rqi_from_score(1.6) == 2
    assert svc.rqi_from_score(3.6) == 4
    assert svc.rqi_from_score(9.0) == 4     # clipped high


def test_rqi_from_score_tuned_thresholds():
    svc = make_service(thresholds=[1.62, 2.48, 3.35])
    assert svc.rqi_from_score(1.0) == 1
    assert svc.rqi_from_score(1.61) == 1    # below first cut
    assert svc.rqi_from_score(1.63) == 2
    assert svc.rqi_from_score(2.47) == 2
    assert svc.rqi_from_score(2.49) == 3
    assert svc.rqi_from_score(3.34) == 3
    assert svc.rqi_from_score(3.36) == 4
    assert svc.rqi_from_score(5.0) == 4


def test_thresholds_monotonic_classes():
    svc = make_service(thresholds=[1.5, 2.5, 3.5])
    scores = [x / 10 for x in range(8, 45)]
    classes = [svc.rqi_from_score(s) for s in scores]
    assert classes == sorted(classes)
    assert set(classes) == {1, 2, 3, 4}


# --- artifact contract validation ------------------------------------------

def _full_artifact():
    art = {k: object() for k in EXPECTED_V2_KEYS} | {"pipeline": object()}
    art["feature_recipe"] = {"name": "cls+patch", "keys": ["cls", "patch"]}
    return art


def test_validate_artifact_ok_returns_no_warnings():
    assert validate_artifact(_full_artifact()) == []


def test_validate_artifact_missing_pipeline_raises():
    art = _full_artifact()
    del art["pipeline"]
    with pytest.raises(ValueError, match="required key"):
        validate_artifact(art)


def test_validate_artifact_not_a_dict_raises():
    with pytest.raises(ValueError, match="must be a dict"):
        validate_artifact(["not", "a", "dict"])


def test_validate_artifact_bad_recipe_raises():
    art = _full_artifact()
    art["feature_recipe"] = {"name": "x"}  # no 'keys'
    with pytest.raises(ValueError, match="no 'keys'"):
        validate_artifact(art)


def test_validate_artifact_missing_v2_metadata_warns_not_raises():
    # structurally usable (has pipeline) but missing v2 metadata -> warnings only
    warnings = validate_artifact({"pipeline": object()})
    assert warnings  # non-empty
    assert any("thresholds" in w for w in warnings)


# ----- canonical-scale boundary (phase-2 direction flip readiness) ---------

class _FakeCalibrator:
    """P(bad) rises with the raw (severity) score; records what it was given."""

    def __init__(self):
        self.seen = []

    def predict(self, xs):
        self.seen.extend(xs)
        return [min(1.0, max(0.0, (x - 1.0) / 3.0)) for x in xs]


def _flipped_scale():
    from app.core.rqi_scale import SCALE
    return SCALE.mirrored()


def test_scale_boundary_is_identity_today():
    svc = make_service(thresholds=[1.62, 2.48, 3.35])
    svc.p_bad_calibrator = _FakeCalibrator()
    assert svc.scale_direction == "lower_is_better"
    assert svc.rqi_from_score(2.49) == 3
    assert svc.p_bad_from_score(2.5) == pytest.approx(0.5)
    assert svc.p_bad_calibrator.seen == [2.5]


def test_flipped_scale_mirrors_levels_and_keeps_p_bad():
    """With a 5 = best scale, a severity-trained artifact needs no retrain:
    levels mirror (x -> 6 - x) and P(bad) is unchanged."""
    ref = make_service(thresholds=[1.62, 2.48, 3.35])
    ref.p_bad_calibrator = _FakeCalibrator()
    flip = make_service(thresholds=[1.62, 2.48, 3.35])
    flip.p_bad_calibrator = _FakeCalibrator()
    flip.scale = _flipped_scale()
    for raw in (1.0, 1.61, 1.63, 2.47, 2.49, 3.34, 3.36, 5.0):
        canonical = flip._to_canonical(raw)
        assert canonical == pytest.approx(6 - raw)
        assert flip.rqi_from_score(canonical) == 6 - ref.rqi_from_score(raw)
        assert flip.p_bad_from_score(canonical) == pytest.approx(ref.p_bad_from_score(raw))
    assert flip.p_bad_calibrator.seen == pytest.approx(ref.p_bad_calibrator.seen)
