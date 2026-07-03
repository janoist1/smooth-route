"""Unit tests for DinoInferenceService decision logic (no torch model load)."""
from app.services.dino_service import DinoInferenceService


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
