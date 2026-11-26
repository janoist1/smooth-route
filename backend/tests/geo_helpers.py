"""Tiny helpers for building test geometry in metres around a reference point."""
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
