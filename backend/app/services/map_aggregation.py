"""Zoom-aware grid aggregation for the map's "honest overview".

Pure helpers so they can be unit-tested without a database. The GROUP BY runs
in the roadQualityGrid resolver; here we only decide the grid coarseness per
zoom. Colour is chosen client-side from each cell's AVERAGE RQI — deliberately
density-independent, so a densely-sampled good road stays green (a leaflet.heat
additive heatmap would falsely light it up as coverage piled up).
"""
from __future__ import annotations

# At or above this Leaflet zoom the client shows individual (clickable) points
# instead of the grid — close in there are few points and the user wants to
# inspect specific roads.
GRID_MAX_ZOOM = 14

# Web-Mercator tile math: one 256px tile spans 360/2^zoom degrees of longitude.
# offset +5 ≈ one cell per ~8 screen px at any zoom (256 / 2^5), fine enough to
# follow road shapes without looking blocky. Populated cells are bounded by data
# coverage (empty cells yield no rows), so a fine grid is cheap.
_GRID_CELL_EXPONENT_OFFSET = 5

_MIN_ZOOM = 0
_MAX_ZOOM = 22


def grid_cell_size_for_zoom(zoom: int) -> float:
    """Grid cell size in degrees for the quality grid at a Leaflet zoom level.

    Monotonically decreasing in zoom: coarse cells when zoomed out, fine cells
    when zoomed in.
    """
    z = max(_MIN_ZOOM, min(_MAX_ZOOM, int(zoom)))
    return 360.0 / (2 ** (z + _GRID_CELL_EXPONENT_OFFSET))


def should_show_grid(zoom: int) -> bool:
    """True when the given zoom should render the quality grid (not raw points)."""
    return int(zoom) < GRID_MAX_ZOOM
