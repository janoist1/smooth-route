"""Speed context for route scoring (pure, stdlib only).

Labels stay surface-only; speed only enters route COMPARISON (T-47): a
defect matters more at 90 km/h than at 30 km/h.

Speed of a segment: the OSM ``maxspeed`` tag (parsed at segment build time,
``road_segments.maxspeed_kmh``) when present, else a default by OSM
``highway`` class, else a fallback — all in ``config/route_scoring.json``.

Impact score of a route (lower is better, 0 = every measured metre Kiváló):

    impact = Σ badness × speed_factor × metres  /  measured metres
    badness      = how many levels the segment's score is below the best level
                   (|score − best|, so it works whichever way the scale runs)
    speed_factor = segment speed / reference speed (50 km/h → 1.0)

In plain words: the average number of levels below Kiváló per measured metre,
where a metre at 90 km/h counts 1.8× and one at 30 km/h 0.6×.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Optional

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "route_scoring.json")

_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh)?\s*$", re.I)


@lru_cache(maxsize=1)
def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def parse_maxspeed(tag: Optional[str], cfg: Optional[dict] = None) -> Optional[int]:
    """OSM maxspeed tag -> km/h, or None when unusable ("none", "signals", …).
    "50", "30 mph", "HU:urban" (zone table); "30;50" takes the highest."""
    if not tag:
        return None
    zones = (cfg or load_config()).get("maxspeed_zones_kmh", {})
    best: Optional[float] = None
    for part in str(tag).split(";"):
        part = part.strip()
        m = _NUMBER.match(part)
        value = None
        if m:
            value = float(m.group(1)) * (1.609344 if (m.group(2) or "").lower() == "mph" else 1.0)
        elif part in zones:
            value = float(zones[part])
        if value is not None and value > 0 and (best is None or value > best):
            best = value
    return None if best is None else int(round(best))


def speed_kmh(maxspeed_kmh: Optional[float], highway: Optional[str],
              cfg: Optional[dict] = None) -> float:
    cfg = cfg or load_config()
    if maxspeed_kmh and maxspeed_kmh > 0:
        return float(maxspeed_kmh)
    return float(cfg.get("default_kmh_by_highway", {}).get(highway or "", cfg.get("fallback_kmh", 50)))


def speed_factor(speed: float, cfg: Optional[dict] = None) -> float:
    cfg = cfg or load_config()
    return max(0.0, float(speed)) / float(cfg.get("reference_kmh", 50))


def badness(score: float, best_level: float) -> float:
    """Levels below the best level (0 at Kiváló), direction-free."""
    return abs(float(score) - float(best_level))
