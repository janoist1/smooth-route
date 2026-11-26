"""YOLO display rule (Era 14 / T-73): suggestions default to conf >= 0.5."""
import json
from pathlib import Path

import pytest

SETTINGS = Path(__file__).resolve().parents[1] / "config" / "analysis_settings.json"


def test_display_threshold_is_configured_at_half():
    entries = {e["key"]: e for e in json.loads(SETTINGS.read_text(encoding="utf-8"))}
    assert entries["yolo_display_conf"]["value"] == 0.5
    # stored/raw detections keep the (lower) inference threshold
    assert entries["yolo_inference_conf"]["value"] < entries["yolo_display_conf"]["value"]


def test_auto_detect_defaults_to_the_display_threshold(monkeypatch):
    pytest.importorskip("cv2")
    from app.core.settings_manager import settings_manager
    from app.services import review_service as rs

    seen = {}

    def fake_detect(image_path, conf_threshold=None, classes=None):
        seen["conf"] = conf_threshold
        return [{"label": "pothole", "confidence": 0.7, "points": [[0, 0], [1, 0], [1, 1]]}]

    monkeypatch.setattr(rs.inference_service, "detect_objects", fake_detect)
    monkeypatch.setattr(settings_manager, "get_setting",
                        lambda key, default=None: 0.5 if key == "yolo_display_conf" else default)
    svc = rs.ReviewService() if hasattr(rs, "ReviewService") else rs.review_service
    monkeypatch.setattr(svc, "_resolve_image_path", lambda f: f)
    out = svc._handle_auto_detect({"filename": "x.jpg"})
    assert seen["conf"] == 0.5
    assert out["annotations"][0]["score"] == 0.7
    svc._handle_auto_detect({"filename": "x.jpg", "confThreshold": 0.2})   # owner override
    assert seen["conf"] == 0.2
