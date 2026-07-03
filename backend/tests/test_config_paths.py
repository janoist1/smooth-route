"""Tests for the single canonical data directory."""

from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT, Settings
from app.core.paths import image_path


def test_relative_data_dir_is_anchored_to_project_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    configured = Settings(DATA_DIR="custom-data")

    assert configured.resolve_data_dir() == str(
        (PROJECT_ROOT / "custom-data").resolve()
    )


def test_absolute_data_dir_is_preserved(tmp_path):
    configured = Settings(DATA_DIR=str(tmp_path / "external-data"))

    assert configured.resolve_data_dir() == str((tmp_path / "external-data").resolve())


@pytest.mark.parametrize("filename", ["../secret.jpg", "nested/image.jpg", ""])
def test_image_path_rejects_non_bare_filenames(filename):
    with pytest.raises(ValueError, match="Invalid image filename"):
        image_path(filename)
