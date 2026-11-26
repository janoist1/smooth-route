"""Canonical RQI scale: one definition for backend, ML and (mirrored) frontend.

Source of truth: ``shared/rqi_scale.json`` (rules: ``shared/README.md``). This
module reads the byte-identical copy next to it (``rqi_scale.json``) so it also
works on Vercel, where only ``backend/`` is deployed; a test fails if the copy
drifts from the shared file.

Stdlib only (no torch, numpy or DB): the ML scripts load this same file by path.

Write scale logic through these helpers, never as bare numbers:

* ordering: ``at_or_better`` / ``at_or_worse`` / ``better_than`` /
  ``worse_than`` (they only use ``<``/``<=``/``>``/``>=``, so they work on
  floats AND on SQLAlchemy column expressions);
* levels by key: ``SCALE.value_of("good")``, not ``2``;
* "bad road": ``SCALE.is_bad(x)``, meaning ``x`` is at or worse than ``bad_from``;
* rounding a continuous score: ``nearest`` / ``toward_worse``;
* orientation: models, YOLO damage bands and tuned cut-points live in a fixed
  **severity** orientation (1 = best, higher = worse, today's numbering). Values
  cross into the canonical scale with ``from_severity`` / ``convert`` and back
  with ``to_severity`` / ``to_direction``. Today these are identities. If
  ``direction`` flips, they map ``x -> min + max - x`` (6 - x on 1-5), so the
  trained models and their gate metrics stay exactly as they are.
"""
from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

LOWER_IS_BETTER = "lower_is_better"
HIGHER_IS_BETTER = "higher_is_better"
DIRECTIONS = (LOWER_IS_BETTER, HIGHER_IS_BETTER)

# The fixed orientation of model scores, model cut-points and the YOLO
# damage% bands (1 = best). Artifacts record it as ``scale_direction``.
SEVERITY = LOWER_IS_BETTER

SCALE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rqi_scale.json")

_LEVEL_FIELDS = ("value", "key", "label_hu", "label_en", "color", "rubric_hu", "rubric_en")


@dataclass(frozen=True)
class RqiLevel:
    value: int
    key: str
    label_hu: str
    label_en: str
    color: str
    rubric_hu: str
    rubric_en: str


class RqiScale:
    """Parsed, validated RQI scale with direction-aware helpers."""

    def __init__(self, data: Dict[str, Any]):
        direction = data.get("direction")
        if direction not in DIRECTIONS:
            raise ValueError(f"rqi scale: direction must be one of {DIRECTIONS}, got {direction!r}")
        raw_levels = data.get("levels") or []
        levels = []
        for raw in raw_levels:
            missing = [f for f in _LEVEL_FIELDS if f not in raw]
            if missing:
                raise ValueError(f"rqi scale: level {raw!r} is missing {missing}")
            levels.append(RqiLevel(**{f: raw[f] for f in _LEVEL_FIELDS}))
        values = [lv.value for lv in levels]
        if not values or sorted(values) != list(range(min(values), max(values) + 1)):
            raise ValueError(f"rqi scale: level values must be consecutive integers, got {values}")
        keys = [lv.key for lv in levels]
        if len(set(keys)) != len(keys):
            raise ValueError(f"rqi scale: duplicate level keys {keys}")

        self.data = data
        self.version: int = int(data.get("version", 1))
        self.direction: str = direction
        self.min_value: int = min(values)
        self.max_value: int = max(values)
        self._by_value = {lv.value: lv for lv in levels}
        self._by_key = {lv.key: lv for lv in levels}
        # best -> worst, whatever the numeric direction
        self.levels: Tuple[RqiLevel, ...] = tuple(
            sorted(levels, key=lambda lv: lv.value, reverse=not self.lower_is_better)
        )
        self.bad_from: int = int(data["bad_from"])
        if self.bad_from not in self._by_value:
            raise ValueError(f"rqi scale: bad_from {self.bad_from} is not a level")
        model_levels = [int(v) for v in data.get("model_levels") or values]
        if any(v not in self._by_value for v in model_levels):
            raise ValueError(f"rqi scale: model_levels {model_levels} contain an unknown level")
        # best -> worst, like ``levels``
        self.model_levels: Tuple[int, ...] = tuple(
            v for v in (lv.value for lv in self.levels) if v in set(model_levels)
        )
        unknown = data.get("unknown") or {}
        self.unknown_label_hu: str = unknown.get("label_hu", "Nincs adat")
        self.unknown_label_en: str = unknown.get("label_en", "Unknown")
        self.unknown_color: str = unknown.get("color", "#888")

    # ----- lookup ---------------------------------------------------------
    @property
    def lower_is_better(self) -> bool:
        return self.direction == LOWER_IS_BETTER

    @property
    def values(self) -> Tuple[int, ...]:
        """All level values, best -> worst."""
        return tuple(lv.value for lv in self.levels)

    @property
    def best(self) -> int:
        return self.levels[0].value

    @property
    def worst(self) -> int:
        return self.levels[-1].value

    def level(self, value: Any) -> RqiLevel:
        """The level for an exact integer value (``KeyError`` otherwise)."""
        v = int(value)
        if v != value or v not in self._by_value:
            raise KeyError(f"not an RQI level: {value!r}")
        return self._by_value[v]

    def value_of(self, key: str) -> int:
        """Numeric value of a level key, e.g. ``value_of("fair")``."""
        return self._by_key[key].value

    def label(self, value: Optional[float], lang: str = "hu") -> str:
        """Label of the nearest level (ties toward the better one); unknown for None."""
        if value is None:
            return self.unknown_label_hu if lang == "hu" else self.unknown_label_en
        lv = self.level(self.nearest(value))
        return lv.label_hu if lang == "hu" else lv.label_en

    # ----- ordering (float- and SQLAlchemy-safe) --------------------------
    def at_or_better(self, x, ref):
        return x <= ref if self.lower_is_better else x >= ref

    def at_or_worse(self, x, ref):
        return x >= ref if self.lower_is_better else x <= ref

    def better_than(self, x, ref):
        return x < ref if self.lower_is_better else x > ref

    def worse_than(self, x, ref):
        return x > ref if self.lower_is_better else x < ref

    def is_bad(self, x):
        """True when ``x`` is at or worse than ``bad_from`` (the P(bad) event)."""
        return self.at_or_worse(x, self.bad_from)

    def worst_first_key(self, x: float) -> float:
        """``sorted(xs, key=SCALE.worst_first_key)`` puts the worst road first."""
        return -self.to_severity(x)

    def midpoint(self, key_a: str, key_b: str) -> float:
        """Halfway between two levels, e.g. the fair|poor boundary (3.5 today)."""
        return (self.value_of(key_a) + self.value_of(key_b)) / 2.0

    # ----- rounding a continuous score to a level -------------------------
    def clamp(self, x: float) -> float:
        return min(self.max_value, max(self.min_value, x))

    def nearest(self, score: float, ties: str = "better") -> int:
        """Nearest level, clamped; exact halves go to the better (default) or worse level."""
        if ties not in ("better", "worse"):
            raise ValueError("ties must be 'better' or 'worse'")
        s = self.to_severity(score)
        k = math.ceil(s - 0.5) if ties == "better" else math.floor(s + 0.5)
        return int(self.from_severity(self._clamp_int(k)))

    def toward_worse(self, score: float) -> int:
        """Round toward the worse level (2.01 -> 3 today), clamped."""
        return int(self.from_severity(self._clamp_int(math.ceil(self.to_severity(score)))))

    def _clamp_int(self, k: int) -> int:
        return int(min(self.max_value, max(self.min_value, k)))

    # ----- orientation ----------------------------------------------------
    def flip(self, x):
        """Mirror a value on the scale: ``min + max - x`` (6 - x on 1-5)."""
        return self.min_value + self.max_value - x

    def convert(self, x, from_direction: str):
        """A value expressed in ``from_direction`` -> canonical value."""
        if from_direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {from_direction!r}")
        return x if from_direction == self.direction else self.flip(x)

    def to_direction(self, x, to_direction: str):
        """Canonical value -> the same point expressed in ``to_direction``."""
        if to_direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {to_direction!r}")
        return x if to_direction == self.direction else self.flip(x)

    def from_severity(self, x):
        return self.convert(x, SEVERITY)

    def to_severity(self, x):
        return self.to_direction(x, SEVERITY)

    def severity_values(self, values: Iterable[int]) -> list:
        """Canonical levels -> sorted severity numbers (e.g. model_levels -> [1, 2, 3, 4])."""
        return sorted(int(self.to_severity(v)) for v in values)

    def mirrored_data(self) -> Dict[str, Any]:
        """This scale's JSON with the numbers mirrored and the direction flipped.

        Same levels, labels, colours and bad-road boundary; only the numbering
        changes (1 = best <-> 5 = best). Used by the phase-2 flip tooling and tests.
        """
        data = copy.deepcopy(self.data)
        data["direction"] = HIGHER_IS_BETTER if self.lower_is_better else LOWER_IS_BETTER
        for lv in data["levels"]:
            lv["value"] = int(self.flip(lv["value"]))
        data["bad_from"] = int(self.flip(self.bad_from))
        data["model_levels"] = sorted(int(self.flip(v)) for v in self.model_levels)
        return data

    def mirrored(self) -> "RqiScale":
        return RqiScale(self.mirrored_data())


def load_scale(path: str = SCALE_PATH) -> RqiScale:
    with open(path, encoding="utf-8") as f:
        return RqiScale(json.load(f))


SCALE = load_scale()
