"""Reanalysis must retain outputs owned by the other pipeline stages."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.core.rqi_scale import SCALE


@pytest.fixture
def road_quality(monkeypatch):
    # Exercise the actual orchestrator without importing torch, OpenCV or YOLO.
    dino = ModuleType("app.services.dino_service")
    dino.dino_service = SimpleNamespace(
        predict_score=lambda path: float(SCALE.value_of("good")),
        rqi_from_score=lambda score: SCALE.value_of("good"),
        p_bad_from_score=lambda score: 0.12,
    )
    analyzer = ModuleType("app.services.road_analyzer")
    analyzer.RoadDamageAnalyzer = lambda: SimpleNamespace()
    monkeypatch.setitem(sys.modules, dino.__name__, dino)
    monkeypatch.setitem(sys.modules, analyzer.__name__, analyzer)
    spec = importlib.util.spec_from_file_location(
        "road_quality_under_test",
        Path(__file__).resolve().parents[1] / "app/services/road_quality.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnalysisSession:
    def __init__(self, image):
        self.image = image
        self.committed = self.closed = False

    def query(self, model):
        return self

    def all(self):
        return [self.image]

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.mark.parametrize("extra_metadata", [{}, {
    "dino_score": float(SCALE.worst), "dino_p_bad": 1.0,
    "frame_quality": {"usable": True},
}])
def test_yolo_reanalysis_preserves_dino_and_frame_quality_metadata(road_quality, monkeypatch, extra_metadata):
    previous = {
        "dino_score": float(SCALE.value_of("good")), "dino_p_bad": 0.12,
        "dino_artifact": "champion", "dino_timestamp": "before",
        "frame_quality": {"usable": False, "reasons": ["photosphere"]},
        "damage_percent": 10.0,
    }
    image = SimpleNamespace(image_url="images/frame.jpg", dino_rqi_score=float(SCALE.best),
                            analysis_metadata=previous)
    db = AnalysisSession(image)
    monkeypatch.setattr(road_quality, "SessionLocal", lambda: db)
    service = road_quality.RoadQualityService()
    monkeypatch.setattr(service, "_resolve_image_path", lambda path: path)
    monkeypatch.setattr(service, "analyze_image", lambda path: SimpleNamespace(
        rqi_score=float(SCALE.best), damage_count=2, damage_types={"pothole": 2},
        analysis_metadata={"damage_percent": 0.1} | extra_metadata,
    ))
    result = service.analyze_points(strategy="YOLO", reanalyze=True)
    assert result["analyzed"] == 1
    assert image.analysis_metadata == previous | {"damage_percent": 0.1}
    assert previous["damage_percent"] == 10.0  # assign a fresh JSON object for ORM tracking
    assert image.dino_rqi_score == float(SCALE.best)
    assert image.damage_count == 2 and image.damage_types == {"pothole": 2}
    assert db.committed and db.closed


def test_classification_reanalysis_preserves_quality_and_yolo_metadata(road_quality, monkeypatch):
    previous = {"frame_quality": {"usable": False}, "damage_percent": 7.5}
    image = SimpleNamespace(image_url="images/frame.jpg", analysis_metadata=previous)
    db = AnalysisSession(image)
    monkeypatch.setattr(road_quality, "SessionLocal", lambda: db)
    service = road_quality.RoadQualityService()
    monkeypatch.setattr(service, "_resolve_image_path", lambda path: path)
    assert service.analyze_points(strategy="CLASSIFICATION", reanalyze=True)["analyzed"] == 1
    assert image.analysis_metadata["frame_quality"] == previous["frame_quality"]
    assert image.analysis_metadata["damage_percent"] == previous["damage_percent"]
    assert image.analysis_metadata["dino_score"] == float(SCALE.value_of("good"))
