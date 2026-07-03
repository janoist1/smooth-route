"""Canonical filesystem paths derived from the configured data directory."""

from pathlib import Path

from app.core.config import settings


def data_dir() -> Path:
    return Path(settings.resolve_data_dir())


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)


def image_path(filename: str) -> Path:
    """Return a safe path for one bare image filename."""
    candidate = Path(filename)
    if candidate.name != filename or filename in {"", ".", ".."}:
        raise ValueError(f"Invalid image filename: {filename}")
    return data_path("images", filename)


def resolve_stored_image(image_url: str) -> Path | None:
    """Resolve a local stored image URL against the sole canonical image tree."""
    if image_url.startswith(("http://", "https://")):
        return None
    candidate = image_path(Path(image_url).name)
    return candidate if candidate.is_file() else None
