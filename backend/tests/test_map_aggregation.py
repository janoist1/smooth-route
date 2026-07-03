"""Unit tests for quality-grid sizing (pure; the SQL GROUP BY runs live)."""
from app.services.map_aggregation import (
    GRID_MAX_ZOOM,
    grid_cell_size_for_zoom,
    should_show_grid,
)


def test_grid_size_strictly_decreasing_in_zoom():
    sizes = [grid_cell_size_for_zoom(z) for z in range(0, 20)]
    assert all(a > b for a, b in zip(sizes, sizes[1:]))


def test_grid_size_halves_per_zoom_step():
    assert grid_cell_size_for_zoom(9) == grid_cell_size_for_zoom(8) / 2


def test_grid_size_clamps_extreme_zooms():
    assert grid_cell_size_for_zoom(-5) == grid_cell_size_for_zoom(0)
    assert grid_cell_size_for_zoom(999) == grid_cell_size_for_zoom(22)


def test_grid_size_positive():
    assert grid_cell_size_for_zoom(22) > 0


def test_should_show_grid_threshold():
    assert should_show_grid(GRID_MAX_ZOOM - 1) is True
    assert should_show_grid(GRID_MAX_ZOOM) is False
    assert should_show_grid(GRID_MAX_ZOOM + 3) is False
