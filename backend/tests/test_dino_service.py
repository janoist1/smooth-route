"""Unit tests for DinoInferenceService decision logic (no torch model load).

dino_service imports torch/numpy/PIL at module level, so on torch-free
environments (CI) this module is skipped; it runs fully on the dev machine.
"""
import pytest

pytest.importorskip("torch")

from app.core.rqi_scale import SCALE
from app.services.dino_service import (DinoInferenceService, EXPECTED_V2_KEYS,
                                       validate_artifact)

# The artifact works in severity (1 = best); its public API in the canonical
# scale. Writing expectations as sv(severity) keeps them valid for either
# numbering (see tests/test_rqi_scale.py).
sv = SCALE.from_severity


def make_service(thresholds=None):
    svc = DinoInferenceService.__new__(DinoInferenceService)
    svc.thresholds = thresholds
    svc.rqi_clip = (1, 4)
    return svc


def test_rqi_from_score_fallback_rounding():
    svc = make_service(thresholds=None)
    assert svc.rqi_from_score(sv(0.4)) == sv(1)     # clipped low
    assert svc.rqi_from_score(sv(1.4)) == sv(1)
    assert svc.rqi_from_score(sv(1.6)) == sv(2)
    assert svc.rqi_from_score(sv(3.6)) == sv(4)
    assert svc.rqi_from_score(sv(9.0)) == sv(4)     # clipped high


def test_rqi_from_score_tuned_thresholds():
    svc = make_service(thresholds=[1.62, 2.48, 3.35])
    assert svc.rqi_from_score(sv(1.0)) == sv(1)
    assert svc.rqi_from_score(sv(1.61)) == sv(1)    # below first cut
    assert svc.rqi_from_score(sv(1.63)) == sv(2)
    assert svc.rqi_from_score(sv(2.47)) == sv(2)
    assert svc.rqi_from_score(sv(2.49)) == sv(3)
    assert svc.rqi_from_score(sv(3.34)) == sv(3)
    assert svc.rqi_from_score(sv(3.36)) == sv(4)
    assert svc.rqi_from_score(sv(5.0)) == sv(4)


def test_thresholds_monotonic_classes():
    svc = make_service(thresholds=[1.5, 2.5, 3.5])
    scores = [x / 10 for x in range(8, 45)]  # severity, best -> worst
    classes = [SCALE.to_severity(svc.rqi_from_score(sv(s))) for s in scores]
    assert classes == sorted(classes)
    assert set(classes) == {1, 2, 3, 4}
    assert {svc.rqi_from_score(sv(s)) for s in scores} == set(SCALE.model_levels)


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


def _severity_level(raw, thresholds):
    """The artifact's own decision, in severity (what training/gate measure)."""
    return 1 + sum(1 for t in thresholds if raw >= t)


@pytest.mark.parametrize("scale", [SCALE, SCALE.mirrored()], ids=["current", "mirrored"])
def test_boundary_converts_levels_and_keeps_p_bad(scale):
    """A severity-trained artifact serves either numbering without retraining:
    levels are the artifact's severity decision expressed on the scale, and
    P(bad) is the calibrator's output for the untouched raw score."""
    th = [1.62, 2.48, 3.35]
    svc = make_service(thresholds=th)
    svc.scale = scale
    svc.p_bad_calibrator = _FakeCalibrator()
    assert svc.scale_direction == "lower_is_better"  # every artifact so far
    raws = (1.0, 1.61, 1.63, 2.47, 2.49, 3.34, 3.36, 5.0)
    for raw in raws:
        canonical = svc._to_canonical(raw)
        assert canonical == pytest.approx(scale.from_severity(raw))
        assert svc.rqi_from_score(canonical) == scale.from_severity(_severity_level(raw, th))
        assert svc.p_bad_from_score(canonical) == pytest.approx(min(1.0, (raw - 1.0) / 3.0))
    assert svc.p_bad_calibrator.seen == pytest.approx(list(raws))


def test_mirrored_scale_mirrors_levels():
    ref = make_service(thresholds=[1.62, 2.48, 3.35])
    flip = make_service(thresholds=[1.62, 2.48, 3.35])
    flip.scale = SCALE.mirrored()
    for raw in (1.0, 1.63, 2.49, 3.36):
        c_ref, c_flip = ref._to_canonical(raw), flip._to_canonical(raw)
        assert c_flip == pytest.approx(6 - c_ref)
        assert flip.rqi_from_score(c_flip) == 6 - ref.rqi_from_score(c_ref)
