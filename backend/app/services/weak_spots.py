"""Configurable Era 16 label targets, with shared thinning and blind order.

Only load_config reads disk; matching and selection need neither DB nor model.
Frame scores and cut-points are severity-oriented, as in label_queue.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence

from app.core.rqi_scale import SCALE, RqiScale
from app.services import label_queue as lq

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "weak_spots.json"


@dataclass(frozen=True)
class Rule:
    key: str
    share: float
    predicted_level: Optional[str] = None
    highways: tuple[str, ...] = ()
    bbox: Optional[tuple[float, float, float, float]] = None  # south, west, north, east
    area: Optional[str] = None
    unlabelled_cells: bool = False


@dataclass(frozen=True)
class Config:
    thin_radius_m: float
    rules: tuple[Rule, ...]


def config_from_dict(data: dict) -> Config:
    radius = float(data["thin_radius_m"])
    if not math.isfinite(radius) or radius < lq.DUP_RADIUS_M:
        raise ValueError("weak spots: thinning must be at least the queue duplicate radius")
    rules = []
    for raw in data["rules"]:
        rule = Rule(**{**raw, "highways": tuple(raw.get("highways", ())),
                       "bbox": tuple(raw["bbox"]) if raw.get("bbox") else None})
        if not math.isfinite(rule.share) or rule.share < 0:
            raise ValueError("weak spots: shares must be finite and non-negative")
        if rule.predicted_level is not None:
            if SCALE.value_of(rule.predicted_level) not in SCALE.model_levels:
                raise ValueError("weak spots: target level is not predicted by the model")
        if rule.area is not None and rule.area not in (*lq.AREAS, lq.OTHER_AREA):
            raise ValueError("weak spots: unknown collection area")
        if rule.bbox is not None:
            south, west, north, east = rule.bbox
            if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
                raise ValueError("weak spots: invalid south/west/north/east bbox")
        rules.append(rule)
    if not rules or not any(r.share > 0 for r in rules):
        raise ValueError("weak spots: at least one rule must have a positive share")
    if len({r.key for r in rules}) != len(rules):
        raise ValueError("weak spots: rule keys must be unique")
    return Config(thin_radius_m=radius, rules=tuple(rules))


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Read backend/config/weak_spots.json once per process (restart to reload)."""
    return config_from_dict(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def predicted_rqi(score: Optional[float], cuts: Sequence[float],
                  scale: Optional[RqiScale] = None) -> Optional[int]:
    """Use tuned model cut-points, never round a continuous score to a level."""
    if score is None or not math.isfinite(score):
        return None
    levels = (scale or SCALE).model_levels  # best to worst, independent of numeric direction
    return levels[min(sum(score >= c for c in cuts), len(levels) - 1)]


def rule_pools(frames: Sequence[lq.Frame], labelled: Sequence[tuple[float, float]],
               cuts: Sequence[float], config: Config) -> dict[str, list[lq.Frame]]:
    """Independent rule matches, after the caller applies the shared exclusions.

    Rules can overlap; the picker counts a selected frame toward just one rule.
    The fallback uses exactly the diverse strategy's spatial-CV grid.
    """
    labelled_cells = {lq.grid_cell(lat, lon) for lat, lon in labelled}
    pools: dict[str, list[lq.Frame]] = {}
    for rule in config.rules:
        members = []
        for f in frames:
            if rule.predicted_level is not None:
                if predicted_rqi(f.score, cuts) != SCALE.value_of(rule.predicted_level):
                    continue
            if rule.highways and f.highway not in rule.highways:
                continue
            if rule.area is not None and lq.area_of(f.lat, f.lon) != rule.area:
                continue
            if rule.bbox is not None:
                south, west, north, east = rule.bbox
                if not (south <= f.lat < north and west <= f.lon < east):
                    continue
            if rule.unlabelled_cells and lq.grid_cell(f.lat, f.lon) in labelled_cells:
                continue
            members.append(f)
        pools[rule.key] = members
    return pools


def pick(frames: Sequence[lq.Frame], labelled: Sequence[tuple[float, float]],
         limit: int, cuts: Sequence[float], config: Config,
         occupied: Iterable[tuple[float, float]] = (), seed: int = 0) -> list[lq.QueueItem]:
    """Weighted fair selection, then an independent stable hash shuffle.

    A dry/disabled rule yields its slots to the others. Spatial coverage within
    each pool reuses pick_diverse; a single index enforces thinning across ALL
    rules, labelled positions, and frames already held/skipped by the client.
    Rule identity is deliberately not exposed as an item reason or boundary.
    """
    occupied = list(occupied)
    pools = rule_pools(frames, labelled, cuts, config)
    rules = {r.key: r for r in config.rules if r.share > 0}
    # Order every candidate spatially, but thin only in the shared index below:
    # pre-thinning a pool could discard a usable alternative after a cross-rule collision.
    lanes = {key: iter(lq.pick_diverse(pools[key], labelled, len(pools[key]), cuts,
                                      thin_radius_m=0, occupied=occupied, seed=seed))
             for key in rules}
    counts = dict.fromkeys(rules, 0)
    taken = lq.PointIndex(config.thin_radius_m)
    for lat, lon in (*labelled, *occupied):
        taken.add(lat, lon)
    used: set[int] = set()
    out = []
    while lanes and len(out) < limit:
        key = min(lanes, key=lambda k: ((counts[k] + 1) / rules[k].share, k))
        item = next(lanes[key], None)
        if item is None:
            del lanes[key]
            continue
        f = item.frame
        if f.id in used or taken.near(f.lat, f.lon, config.thin_radius_m):
            continue
        used.add(f.id)
        taken.add(f.lat, f.lon)
        counts[key] += 1
        out.append(lq.QueueItem(frame=f, reason=lq.Strategy.WEAK_SPOTS.value,
                                area=item.area, uncertainty=None, cell_labels=item.cell_labels))
    return sorted(out, key=lambda it: (lq.stable_rank(("weak_spots_order", it.frame.id), seed),
                                       it.frame.id))
