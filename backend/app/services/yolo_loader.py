"""Shared, cwd-independent YOLO model resolution and loading."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings

DEFAULT_YOLO_MODEL = "yolov8m-seg.pt"

logger = logging.getLogger(__name__)


def canonical_model_dir() -> Path:
    """Return the configured canonical model directory."""
    return Path(settings.resolve_data_dir()).resolve() / "models"


def _path_inside(directory: Path, name: str) -> Path:
    candidate = (directory / name).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError as exc:
        raise ValueError(f"Model path must stay inside {directory}: {name}") from exc
    return candidate


def resolve_model_path(
    model_name: str,
    *,
    model_dir: Path | None = None,
    fallback_name: str = DEFAULT_YOLO_MODEL,
) -> Path:
    """Resolve a configured model to an existing absolute file path."""
    directory = (model_dir or canonical_model_dir()).resolve()
    requested = Path(model_name).expanduser()
    if requested.is_absolute():
        candidate = requested.resolve()
        try:
            candidate.relative_to(directory)
        except ValueError as exc:
            raise ValueError(
                f"Model path must stay inside {directory}: {model_name}"
            ) from exc
    else:
        candidate = _path_inside(directory, model_name)

    if candidate.is_file():
        return candidate

    fallback = _path_inside(directory, fallback_name)
    if fallback.is_file():
        logger.warning(
            "YOLO model %s was not found; using fallback %s",
            candidate,
            fallback,
        )
        return fallback

    raise FileNotFoundError(
        f"Neither YOLO model '{candidate}' nor fallback '{fallback}' exists"
    )


def _create_yolo(model_path: str) -> Any:
    from ultralytics import YOLO

    return YOLO(model_path)


class YoloModelLoader:
    """Load each YOLO role once and reload it when its resolved path changes."""

    def __init__(
        self,
        *,
        model_dir: Path | None = None,
        model_factory: Callable[[str], Any] | None = None,
    ):
        self._model_dir = model_dir
        self._model_factory = model_factory or _create_yolo
        self._models: dict[str, tuple[Path, Any]] = {}

    def load(
        self,
        role: str,
        model_name: str,
        *,
        fallback_name: str = DEFAULT_YOLO_MODEL,
        force_reload: bool = False,
    ) -> Any:
        model_path = resolve_model_path(
            model_name,
            model_dir=self._model_dir,
            fallback_name=fallback_name,
        )
        cached = self._models.get(role)
        if cached and cached[0] == model_path and not force_reload:
            return cached[1]

        logger.info("Loading YOLO role '%s' from %s", role, model_path)
        model = self._model_factory(str(model_path))
        self._models[role] = (model_path, model)
        return model

    def loaded_path(self, role: str) -> Path | None:
        cached = self._models.get(role)
        return cached[0] if cached else None

    def unload(self, role: str) -> None:
        self._models.pop(role, None)


yolo_model_loader = YoloModelLoader()
