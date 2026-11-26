"""Test helpers for the segment layer: geometry in metres around a reference
point, and pinned aggregation configs."""
import math

ORIGIN = (47.5, 19.05)  # Budapest-ish
_M_PER_DEG = math.pi * 6_371_008.8 / 180.0


def at(east_m: float, north_m: float, origin=ORIGIN) -> tuple[float, float]:
    """(lat, lon) of a point ``east_m`` / ``north_m`` metres from ``origin``."""
    lat = origin[0] + north_m / _M_PER_DEG
    lon = origin[1] + east_m / (_M_PER_DEG * math.cos(math.radians(origin[0])))
    return (lat, lon)


class FakeLine:
    """Minimal object satisfying map_matching.Line."""

    def __init__(self, id, coords):
        self.id = id
        self.coords = coords


# --- Segment-aggregation configs for tests ---------------------------------
# Tests pin their own numbers so retuning backend/config/segment_aggregation.json
# (or flipping the scale there) never changes what a unit test asserts.

BASE_CONFIG = {
    "version": 1,
    "segment_length_m": 150,
    "aggregator": "median_score",
    "trim_fraction": 0.1,
    "thresholds": [1.51, 2.47, 3.18],
    "p_bad_threshold": 0.5,
    "min_images": 3,
    "scale": {"classes": [1, 2, 3, 4], "higher_is_worse": True, "bad_class": 3},
    "confidence": {"n_ref": 8, "spread_ref": 0.6, "margin_ref": 0.3,
                   "high": 0.66, "medium": 0.33},
    "age": {"grace_years": 3, "half_life_years": 5},
}

# The same scale mirrored to "5 = excellent" (x → 6 − x): what the config
# looks like after the planned scale flip.
FLIPPED_CONFIG = {
    **BASE_CONFIG,
    "thresholds": [6 - 3.18, 6 - 2.47, 6 - 1.51],
    "scale": {"classes": [2, 3, 4, 5], "higher_is_worse": False, "bad_class": 3},
}


def make_config(**overrides):
    from app.services.segment_aggregation import config_from_dict

    return config_from_dict({**BASE_CONFIG, **overrides})
