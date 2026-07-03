"""Unit tests for cwd-independent YOLO model loading (no torch required)."""

from pathlib import Path

import pytest

from app.services.yolo_loader import YoloModelLoader, resolve_model_path


def _touch_model(model_dir: Path, name: str) -> Path:
    path = model_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path.resolve()


def test_resolve_model_path_is_independent_of_cwd(tmp_path, monkeypatch):
    model_dir = tmp_path / "data" / "models"
    expected = _touch_model(model_dir, "active.pt")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert resolve_model_path("active.pt", model_dir=model_dir) == expected


def test_resolve_model_path_uses_the_shared_fallback(tmp_path):
    model_dir = tmp_path / "models"
    fallback = _touch_model(model_dir, "fallback.pt")

    resolved = resolve_model_path(
        "missing.pt",
        model_dir=model_dir,
        fallback_name="fallback.pt",
    )

    assert resolved == fallback


def test_resolve_model_path_rejects_relative_escape(tmp_path):
    model_dir = tmp_path / "models"
    _touch_model(model_dir, "fallback.pt")

    with pytest.raises(ValueError, match="must stay inside"):
        resolve_model_path(
            "../outside.pt",
            model_dir=model_dir,
            fallback_name="fallback.pt",
        )


def test_resolve_model_path_rejects_absolute_path_outside_model_dir(tmp_path):
    model_dir = tmp_path / "models"
    _touch_model(model_dir, "fallback.pt")
    outside = _touch_model(tmp_path / "outside", "external.pt")

    with pytest.raises(ValueError, match="must stay inside"):
        resolve_model_path(
            str(outside),
            model_dir=model_dir,
            fallback_name="fallback.pt",
        )


def test_loader_caches_and_reloads_when_model_changes(tmp_path):
    model_dir = tmp_path / "models"
    _touch_model(model_dir, "first.pt")
    _touch_model(model_dir, "second.pt")
    loaded_paths: list[str] = []

    def fake_factory(path: str):
        loaded_paths.append(path)
        return object()

    loader = YoloModelLoader(model_dir=model_dir, model_factory=fake_factory)

    first = loader.load("road_damage", "first.pt")
    cached = loader.load("road_damage", "first.pt")
    second = loader.load("road_damage", "second.pt")

    assert cached is first
    assert second is not first
    assert loaded_paths == [
        str((model_dir / "first.pt").resolve()),
        str((model_dir / "second.pt").resolve()),
    ]
