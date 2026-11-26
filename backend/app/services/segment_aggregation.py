"""Per-segment aggregation of frame scores: class, P(bad), confidence (pure).

A road segment (~150 m piece of an OSM way) collects the Street View frames
snapped onto it. This module turns those frames into one verdict, driven
entirely by ``backend/config/segment_aggregation.json`` so the numbers can be
retuned without touching code:

    {"version": 1, "segment_length_m": 150, "aggregator": "median_score",
     "trim_fraction": 0.1, "thresholds": [1.51, 2.47, 3.18],
     "p_bad_threshold": 0.5, "min_images": 3,
     "confidence": {"n_ref": 8, "spread_ref": 0.6, "margin_ref": 0.3,
                    "high": 0.66, "medium": 0.33},
     "age": {"grace_years": 3, "half_life_years": 5}}

Scale reminder: RQI 1 = excellent … 4 = poor. A frame's score is the
continuous DINO estimate (``analysis_metadata.dino_score``), falling back to
the ordinal ``dino_rqi_score``.

Aggregators
-----------
- ``median_score`` / ``mean_score`` / ``trimmed_mean_score``: the aggregated
  score is that statistic of the frame scores; the class is the score cut at
  ``thresholds``.
- ``mean_p_bad``: the score is the median frame score and gives the class, but
  the mean P(bad) GATES the good/bad boundary: P(bad) ≥ ``p_bad_threshold``
  forces class ≥ 3, below it caps the class at 2.

Confidence
----------
    conf = clamp((1 - exp(-n / n_ref))
                 * exp(-(iqr / spread_ref) ** 2)
                 * (0.5 + 0.5 * min(1, margin / margin_ref)), 0, 1)
           * 0.5 ** (max(0, age_years - grace_years) / half_life_years)

``n`` = scored frames, ``iqr`` = interquartile range of their scores, ``margin``
= distance of the aggregated score from the nearest class threshold, age from
the segment's NEWEST capture date (no age factor when unknown). Segments with
fewer than ``min_images`` frames keep their class but are always "low".
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "segment_aggregation.json"

AGGREGATORS = ("median_score", "mean_score", "trimmed_mean_score", "mean_p_bad")

LEVEL_HIGH = "high"
LEVEL_MEDIUM = "medium"
LEVEL_LOW = "low"

# RQI ≥ 3 is "bad" — the same definition the calibrated dino_p_bad uses.
BAD_RQI = 3


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfidenceConfig:
    n_ref: float = 8.0
    spread_ref: float = 0.6
    margin_ref: float = 0.3
    high: float = 0.66
    medium: float = 0.33


@dataclass(frozen=True)
class AgeConfig:
    grace_years: float = 3.0
    half_life_years: float = 5.0


@dataclass(frozen=True)
class SegmentConfig:
    version: int = 1
    segment_length_m: float = 150.0
    aggregator: str = "median_score"
    trim_fraction: float = 0.1
    thresholds: tuple[float, float, float] = (1.51, 2.47, 3.18)
    p_bad_threshold: float = 0.5
    min_images: int = 3
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    age: AgeConfig = field(default_factory=AgeConfig)


DEFAULT_CONFIG = SegmentConfig()


def _sub(cls, data: Any, name: str):
    """Build a nested config dataclass from a dict, defaults for missing keys."""
    if data is None:
        return cls()
    if not isinstance(data, Mapping):
        raise ValueError(f"'{name}' must be an object")
    known = {k: float(v) for k, v in data.items() if k in cls.__dataclass_fields__}
    return cls(**known)


def config_from_dict(data: Mapping[str, Any]) -> SegmentConfig:
    """Validate a parsed config. Missing keys fall back to the defaults;
    unknown keys are ignored (forward compatibility); bad values raise
    ``ValueError`` with the reason — a silently wrong aggregation is worse
    than a failed rebuild.
    """
    if not isinstance(data, Mapping):
        raise ValueError("segment aggregation config must be a JSON object")
    d = DEFAULT_CONFIG
    try:
        cfg = SegmentConfig(
            version=int(data.get("version", d.version)),
            segment_length_m=float(data.get("segment_length_m", d.segment_length_m)),
            aggregator=str(data.get("aggregator", d.aggregator)),
            trim_fraction=float(data.get("trim_fraction", d.trim_fraction)),
            thresholds=tuple(float(t) for t in data.get("thresholds", d.thresholds)),
            p_bad_threshold=float(data.get("p_bad_threshold", d.p_bad_threshold)),
            min_images=int(data.get("min_images", d.min_images)),
            confidence=_sub(ConfidenceConfig, data.get("confidence"), "confidence"),
            age=_sub(AgeConfig, data.get("age"), "age"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid segment aggregation config: {exc}") from exc

    if cfg.aggregator not in AGGREGATORS:
        raise ValueError(f"aggregator must be one of {AGGREGATORS}, got {cfg.aggregator!r}")
    if cfg.segment_length_m <= 0:
        raise ValueError("segment_length_m must be > 0")
    if len(cfg.thresholds) != 3 or list(cfg.thresholds) != sorted(cfg.thresholds):
        raise ValueError("thresholds must be 3 ascending numbers")
    if not 0.0 <= cfg.trim_fraction < 0.5:
        raise ValueError("trim_fraction must be in [0, 0.5)")
    if not 0.0 <= cfg.p_bad_threshold <= 1.0:
        raise ValueError("p_bad_threshold must be in [0, 1]")
    if cfg.min_images < 1:
        raise ValueError("min_images must be >= 1")
    c = cfg.confidence
    if min(c.n_ref, c.spread_ref, c.margin_ref) <= 0:
        raise ValueError("confidence n_ref / spread_ref / margin_ref must be > 0")
    if not 0.0 <= c.medium <= c.high <= 1.0:
        raise ValueError("confidence levels must satisfy 0 <= medium <= high <= 1")
    if cfg.age.grace_years < 0 or cfg.age.half_life_years <= 0:
        raise ValueError("age.grace_years must be >= 0 and half_life_years > 0")
    return cfg


_cache: dict[str, tuple[float, SegmentConfig]] = {}


def load_config(path: Optional[Path | str] = None) -> SegmentConfig:
    """Load the config file (re-read when its mtime changes).

    A missing file yields the built-in defaults, so a deploy that does not
    ship ``backend/config`` still serves the layer. A present-but-invalid file
    raises ``ValueError``.
    """
    p = Path(path) if path else CONFIG_PATH
    try:
        mtime = p.stat().st_mtime
    except OSError:
        logger.warning("segment aggregation config %s not found — using defaults", p)
        return DEFAULT_CONFIG
    cached = _cache.get(str(p))
    if cached and cached[0] == mtime:
        return cached[1]
    cfg = config_from_dict(json.loads(p.read_text(encoding="utf-8")))
    _cache[str(p)] = (mtime, cfg)
    return cfg


def with_overrides(cfg: SegmentConfig, **changes: Any) -> SegmentConfig:
    """A validated copy with some top-level fields replaced (CLI overrides)."""
    merged = replace(cfg, **changes)
    return config_from_dict({
        **{k: getattr(merged, k) for k in (
            "version", "segment_length_m", "aggregator", "trim_fraction",
            "thresholds", "p_bad_threshold", "min_images")},
        "confidence": vars(merged.confidence),
        "age": vars(merged.age),
    })


# --------------------------------------------------------------------------
# Per-frame inputs
# --------------------------------------------------------------------------

def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def frame_score(dino_rqi_score: Any, analysis_metadata: Any) -> Optional[float]:
    """Continuous score of one frame: metadata ``dino_score`` → ``dino_rqi_score``."""
    if isinstance(analysis_metadata, Mapping):
        continuous = _finite(analysis_metadata.get("dino_score"))
        if continuous is not None:
            return continuous
    return _finite(dino_rqi_score)


def frame_p_bad(dino_rqi_score: Any, analysis_metadata: Any) -> Optional[float]:
    """P(bad) of one frame: calibrated ``dino_p_bad`` when the frame has it,
    otherwise a hard 0/1 from the ordinal class (bad = RQI ≥ 3), so a segment's
    mean degrades gracefully to "share of bad frames" for older analyses.
    """
    if isinstance(analysis_metadata, Mapping):
        p = _finite(analysis_metadata.get("dino_p_bad"))
        if p is not None:
            return max(0.0, min(1.0, p))
    rqi = _finite(dino_rqi_score)
    if rqi is None:
        return None
    return 1.0 if rqi >= BAD_RQI else 0.0


@dataclass(frozen=True)
class FrameObs:
    """What the aggregation needs from one snapped frame."""

    score: float
    p_bad: Optional[float] = None
    capture_date: Optional[dt.date] = None


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (``q`` in [0, 1]) of SORTED values —
    the same definition as numpy's default."""
    if not sorted_values:
        raise ValueError("percentile of empty data")
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (pos - lo) * (sorted_values[hi] - sorted_values[lo])


def median(values: Sequence[float]) -> float:
    return percentile(sorted(values), 0.5)


def mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def trimmed_mean(values: Sequence[float], trim_fraction: float) -> float:
    """Mean after dropping ``floor(trim_fraction * n)`` values from EACH end."""
    ordered = sorted(values)
    k = int(trim_fraction * len(ordered))
    kept = ordered[k: len(ordered) - k] or ordered
    return mean(kept)


def iqr(values: Sequence[float]) -> float:
    """Interquartile range (0 for a single value)."""
    ordered = sorted(values)
    return percentile(ordered, 0.75) - percentile(ordered, 0.25)


def aggregate_score(scores: Sequence[float], cfg: SegmentConfig) -> float:
    if cfg.aggregator == "mean_score":
        return mean(scores)
    if cfg.aggregator == "trimmed_mean_score":
        return trimmed_mean(scores, cfg.trim_fraction)
    # median_score, and mean_p_bad (whose class comes from the median score)
    return median(scores)


def classify(score: float, thresholds: Sequence[float]) -> int:
    """RQI class 1–4: one more than the number of thresholds at or below it."""
    return 1 + sum(1 for t in thresholds if score >= t)


def threshold_margin(score: float, thresholds: Sequence[float]) -> float:
    """Distance of a score from the nearest class boundary."""
    return min(abs(score - t) for t in thresholds)


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------

def base_confidence(n: int, spread_iqr: float, margin: float, c: ConfidenceConfig) -> float:
    """Confidence before the age factor (see the module docstring)."""
    if n <= 0:
        return 0.0
    value = (
        (1.0 - math.exp(-n / c.n_ref))
        * math.exp(-((spread_iqr / c.spread_ref) ** 2))
        * (0.5 + 0.5 * min(1.0, margin / c.margin_ref))
    )
    return max(0.0, min(1.0, value))


def age_years(capture: Optional[dt.date], today: dt.date) -> Optional[float]:
    """Age of a capture month in years (month precision, never negative)."""
    if capture is None:
        return None
    months = (today.year - capture.year) * 12 + (today.month - capture.month)
    return max(0, months) / 12.0


def age_factor(newest_capture: Optional[dt.date], today: dt.date, a: AgeConfig) -> float:
    """``0.5 ** (max(0, age - grace) / half_life)``; 1.0 when the age is unknown."""
    years = age_years(newest_capture, today)
    if years is None:
        return 1.0
    return 0.5 ** (max(0.0, years - a.grace_years) / a.half_life_years)


def confidence_level(confidence: float, n_images: int, cfg: SegmentConfig) -> str:
    """"high" | "medium" | "low"; below ``min_images`` it is always "low"."""
    if n_images < cfg.min_images:
        return LEVEL_LOW
    if confidence >= cfg.confidence.high:
        return LEVEL_HIGH
    if confidence >= cfg.confidence.medium:
        return LEVEL_MEDIUM
    return LEVEL_LOW


# --------------------------------------------------------------------------
# The aggregate
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SegmentAggregate:
    n_images: int
    score: Optional[float]      # aggregated continuous score, 1–4 scale
    rqi: Optional[int]          # 1–4, None without frames
    p_bad: Optional[float]      # mean frame P(bad)
    confidence: float           # 0–1, after the age factor
    capture_date_min: Optional[dt.date]
    capture_date_max: Optional[dt.date]


EMPTY_AGGREGATE = SegmentAggregate(0, None, None, None, 0.0, None, None)


def aggregate_frames(
    frames: Sequence[FrameObs], cfg: SegmentConfig, today: Optional[dt.date] = None
) -> SegmentAggregate:
    """Aggregate the frames of one segment into class / P(bad) / confidence."""
    if not frames:
        return EMPTY_AGGREGATE
    today = today or dt.date.today()

    scores = [f.score for f in frames]
    score = aggregate_score(scores, cfg)
    rqi = classify(score, cfg.thresholds)

    p_values = [f.p_bad for f in frames if f.p_bad is not None]
    p_bad = mean(p_values) if p_values else None

    if cfg.aggregator == "mean_p_bad" and p_bad is not None:
        # P(bad) decides which side of the good/bad boundary the segment is on;
        # the median score only picks the class within that side.
        if p_bad >= cfg.p_bad_threshold:
            rqi = max(BAD_RQI, rqi)
        else:
            rqi = min(BAD_RQI - 1, rqi)

    dates = [f.capture_date for f in frames if f.capture_date is not None]
    newest = max(dates) if dates else None

    conf = base_confidence(
        len(scores), iqr(scores), threshold_margin(score, cfg.thresholds), cfg.confidence
    ) * age_factor(newest, today, cfg.age)

    return SegmentAggregate(
        n_images=len(scores),
        score=score,
        rqi=rqi,
        p_bad=p_bad,
        confidence=max(0.0, min(1.0, conf)),
        capture_date_min=min(dates) if dates else None,
        capture_date_max=newest,
    )
