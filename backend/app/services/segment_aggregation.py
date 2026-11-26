"""Per-segment aggregation of frame scores: class, P(bad), confidence (pure).

A road segment (a ~200 m piece of a road) collects the Street View frames
snapped onto it. This module turns those frames into one verdict, driven
entirely by ``backend/config/segment_aggregation.json`` so the numbers can be
retuned without touching code:

    {"version": 1, "segment_length_m": 200, "aggregator": "median_score",
     "trim_fraction": 0.0, "thresholds": [2.948, 3.504, 4.423],
     "p_bad_threshold": 0.5, "min_images": 2,
     "scale": {"classes": [2, 3, 4, 5], "higher_is_worse": false, "bad_class": 3},
     "confidence": {"n_ref": 0.5, "spread_ref": 1.5, "margin_ref": 0.5,
                    "high": 0.7, "medium": 0.6},
     "age": {"grace_years": 3, "half_life_years": 5}}

THE RQI SCALE LIVES IN ONE PLACE. Which way the scale runs, which class
labels exist and where "bad" starts are stated only by ``thresholds`` +
``scale`` in that file and interpreted only by ``RqiScale`` below. Nothing
else in the segment layer compares a score or a class against a literal —
flipping the scale (e.g. to 5 = excellent) is an edit of those two config
keys. They have no defaults in code on purpose.

A frame's score is the continuous DINO estimate
(``analysis_metadata.dino_score``), falling back to the ordinal
``dino_rqi_score``. Frames marked ``analysis_metadata.frame_quality.usable =
false`` are left out.

Aggregators
-----------
- ``median_score`` / ``mean_score`` / ``trimmed_mean_score``: the aggregated
  score is that statistic of the frame scores; the class is the score cut at
  ``thresholds``.
- ``mean_p_bad``: the score is the median frame score and gives the class, but
  the mean P(bad) GATES the good/bad boundary: P(bad) ≥ ``p_bad_threshold``
  forces a bad class, below it a good one.

Confidence
----------
    conf = clamp((1 - exp(-n / n_ref))
                 * exp(-(iqr / spread_ref) ** 2)
                 * (0.5 + 0.5 * min(1, margin / margin_ref)), 0, 1)
           * 0.5 ** (max(0, age_years - grace_years) / half_life_years)

``n`` = frames, ``iqr`` = interquartile range of their scores, ``margin`` =
distance of the aggregated score from the nearest class threshold, age from
the segment's NEWEST capture date (no age factor when unknown). Segments with
fewer than ``min_images`` frames keep their class but are always "low".

Unlabelled areas (``unlabelled_area: {radius_km, cap_level}``): a segment
with no human-labelled frame within ``radius_km`` has its confidence capped at
the top of ``cap_level``; when that lowers it, the stored flag makes the
reason "unlabelled_area" (see ``apply_unlabelled_area``).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "segment_aggregation.json"

AGGREGATORS = ("median_score", "mean_score", "trimmed_mean_score", "mean_p_bad")

LEVEL_HIGH = "high"
LEVEL_MEDIUM = "medium"
LEVEL_LOW = "low"

# confidence_reason() values: the factor that limits the confidence most.
REASON_FEW_IMAGES = "few_images"
REASON_DISAGREEMENT = "disagreement"
REASON_NEAR_THRESHOLD = "near_threshold"
REASON_OLD_IMAGES = "old_images"
# Product honesty rule (not a fitted factor): no human label within
# unlabelled_area.radius_km -> confidence capped at the top of cap_level.
REASON_UNLABELLED_AREA = "unlabelled_area"
CAP_LEVELS = (LEVEL_MEDIUM, LEVEL_LOW)


# --------------------------------------------------------------------------
# The RQI scale — the only code that knows its direction
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RqiScale:
    """Direction and class labels of the RQI scale (from the config file).

    ``classes``          class labels in order of ASCENDING score: the label
                         for scores below ``thresholds[0]``, between
                         ``[0]`` and ``[1]``, …, above ``thresholds[-1]``.
    ``higher_is_worse``  True: a larger score/class is a worse road.
    ``bad_class``        this class and every worse one counts as "bad"
                         (what the calibrated ``dino_p_bad`` predicts).

    Since 2026-11-26 ("5 = excellent", shared/rqi_scale.json): classes
    (2, 3, 4, 5), higher_is_worse false, bad_class 3, thresholds mirrored from
    the ML recipe (t → 6 − t, re-sorted). Before: (1, 2, 3, 4), higher is worse.
    backend/tests/test_rqi_scale.py keeps this block equal to the canonical scale.
    """

    classes: tuple[int, ...]
    higher_is_worse: bool
    bad_class: int

    def classify(self, score: float, thresholds: Sequence[float]) -> int:
        """Class of a continuous score. A score exactly on a threshold
        belongs to the WORSE class, whichever way the scale runs."""
        if self.higher_is_worse:
            return self.classes[sum(1 for t in thresholds if score >= t)]
        return self.classes[sum(1 for t in thresholds if score > t)]

    def is_bad(self, value: float) -> bool:
        """Is this class (or ordinal frame score) on the bad side?"""
        return value >= self.bad_class if self.higher_is_worse else value <= self.bad_class

    def gate(self, rqi: int, bad: bool) -> int:
        """Move a class across the good/bad boundary when ``bad`` disagrees
        with it; otherwise return it unchanged."""
        if self.is_bad(rqi) == bad:
            return rqi
        ordered = self.best_to_worst
        boundary = ordered.index(self.bad_class)
        return self.bad_class if bad else ordered[boundary - 1]

    @property
    def best_to_worst(self) -> tuple[int, ...]:
        return self.classes if self.higher_is_worse else tuple(reversed(self.classes))

    @property
    def ascending(self) -> tuple[int, ...]:
        """Class labels sorted by label. (Per-class arrays such as
        ``RouteQuality.lengthByRqi`` use ``best_to_worst`` instead.)"""
        return tuple(sorted(self.classes))

    def badness(self, score: float) -> float:
        """Sort key: larger = worse road."""
        return score if self.higher_is_worse else -score


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
class UnlabelledAreaConfig:
    """Cap the confidence of segments with no human-labelled frame within
    ``radius_km`` at the top of ``cap_level`` ("medium" or "low").

    Not a fitted error model: under spatial CV distance to labels does not
    predict error at 0.1–1.25 km (T-41). It is an honesty rule backed by the
    region-level evidence (leave-region-out QWK 0.66, Budapest 0.24).
    ``radius_km`` 0 switches the rule off.
    """

    radius_km: float = 0.0
    cap_level: str = LEVEL_MEDIUM


@dataclass(frozen=True)
class SegmentConfig:
    # Scale-dependent: REQUIRED in the file, no defaults here (see module doc).
    thresholds: tuple[float, ...]
    scale: RqiScale
    # Scale-independent tuning.
    version: int = 1
    segment_length_m: float = 150.0
    aggregator: str = "median_score"
    trim_fraction: float = 0.1
    p_bad_threshold: float = 0.5
    min_images: int = 3
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    age: AgeConfig = field(default_factory=AgeConfig)
    unlabelled_area: UnlabelledAreaConfig = field(default_factory=UnlabelledAreaConfig)

    def classify(self, score: float) -> int:
        return self.scale.classify(score, self.thresholds)


def _sub(cls, data: Any, name: str):
    """Build a nested config dataclass from a dict, defaults for missing keys."""
    if data is None:
        return cls()
    if not isinstance(data, Mapping):
        raise ValueError(f"'{name}' must be an object")
    known = {k: float(v) for k, v in data.items() if k in cls.__dataclass_fields__}
    return cls(**known)


def _unlabelled_area(data: Any) -> UnlabelledAreaConfig:
    if data is None:
        return UnlabelledAreaConfig()
    if not isinstance(data, Mapping):
        raise ValueError("'unlabelled_area' must be an object")
    d = UnlabelledAreaConfig()
    return UnlabelledAreaConfig(
        radius_km=float(data.get("radius_km", d.radius_km)),
        cap_level=str(data.get("cap_level", d.cap_level)),
    )


def _scale(data: Any) -> RqiScale:
    if not isinstance(data, Mapping):
        raise ValueError("'scale' is required: {classes, higher_is_worse, bad_class}")
    try:
        classes = tuple(int(c) for c in data["classes"])
        higher_is_worse = data["higher_is_worse"]
        bad_class = int(data["bad_class"])
    except KeyError as exc:
        raise ValueError(f"'scale' is missing {exc}") from exc
    if not isinstance(higher_is_worse, bool):
        raise ValueError("scale.higher_is_worse must be true or false")
    if len(classes) < 2 or list(classes) != sorted(set(classes)):
        raise ValueError("scale.classes must be distinct, ascending class labels")
    scale = RqiScale(classes, higher_is_worse, bad_class)
    if bad_class not in classes or bad_class == scale.best_to_worst[0]:
        raise ValueError("scale.bad_class must be one of the classes, and not the best one")
    return scale


def config_from_dict(data: Mapping[str, Any]) -> SegmentConfig:
    """Validate a parsed config. ``thresholds`` and ``scale`` are required;
    other missing keys fall back to defaults; unknown keys are ignored
    (forward compatibility); bad values raise ``ValueError`` with the reason —
    a silently wrong aggregation is worse than a failed rebuild.
    """
    if not isinstance(data, Mapping):
        raise ValueError("segment aggregation config must be a JSON object")
    if "thresholds" not in data:
        raise ValueError("'thresholds' is required")
    scale = _scale(data.get("scale"))
    f = SegmentConfig.__dataclass_fields__
    try:
        cfg = SegmentConfig(
            thresholds=tuple(float(t) for t in data["thresholds"]),
            scale=scale,
            version=int(data.get("version", f["version"].default)),
            segment_length_m=float(data.get("segment_length_m", f["segment_length_m"].default)),
            aggregator=str(data.get("aggregator", f["aggregator"].default)),
            trim_fraction=float(data.get("trim_fraction", f["trim_fraction"].default)),
            p_bad_threshold=float(data.get("p_bad_threshold", f["p_bad_threshold"].default)),
            min_images=int(data.get("min_images", f["min_images"].default)),
            confidence=_sub(ConfidenceConfig, data.get("confidence"), "confidence"),
            age=_sub(AgeConfig, data.get("age"), "age"),
            unlabelled_area=_unlabelled_area(data.get("unlabelled_area")),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid segment aggregation config: {exc}") from exc

    if cfg.aggregator not in AGGREGATORS:
        raise ValueError(f"aggregator must be one of {AGGREGATORS}, got {cfg.aggregator!r}")
    if cfg.segment_length_m <= 0:
        raise ValueError("segment_length_m must be > 0")
    if list(cfg.thresholds) != sorted(cfg.thresholds):
        raise ValueError("thresholds must be ascending")
    if len(cfg.thresholds) != len(scale.classes) - 1:
        raise ValueError("thresholds must have one entry fewer than scale.classes")
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
    u = cfg.unlabelled_area
    if not (math.isfinite(u.radius_km) and u.radius_km >= 0):
        raise ValueError("unlabelled_area.radius_km must be >= 0 (0 = off)")
    if u.cap_level not in CAP_LEVELS:
        raise ValueError(f"unlabelled_area.cap_level must be one of {CAP_LEVELS}")
    return cfg


def config_to_dict(cfg: SegmentConfig) -> dict:
    """The config as plain JSON-able data (inverse of ``config_from_dict``)."""
    return {
        "version": cfg.version,
        "segment_length_m": cfg.segment_length_m,
        "aggregator": cfg.aggregator,
        "trim_fraction": cfg.trim_fraction,
        "thresholds": list(cfg.thresholds),
        "p_bad_threshold": cfg.p_bad_threshold,
        "min_images": cfg.min_images,
        "scale": {
            "classes": list(cfg.scale.classes),
            "higher_is_worse": cfg.scale.higher_is_worse,
            "bad_class": cfg.scale.bad_class,
        },
        "confidence": dict(vars(cfg.confidence)),
        "age": dict(vars(cfg.age)),
        "unlabelled_area": dict(vars(cfg.unlabelled_area)),
    }


_cache: dict[str, tuple[float, SegmentConfig]] = {}


def load_config(path: Optional[Path | str] = None) -> SegmentConfig:
    """Load the config file (re-read when its mtime changes).

    A missing or invalid file raises ``ValueError``: the scale direction and
    the class thresholds exist only there, so there is nothing safe to fall
    back to.
    """
    p = Path(path) if path else CONFIG_PATH
    try:
        mtime = p.stat().st_mtime
    except OSError as exc:
        raise ValueError(f"segment aggregation config not found: {p}") from exc
    cached = _cache.get(str(p))
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"segment aggregation config {p} is not valid JSON: {exc}") from exc
    cfg = config_from_dict(data)
    _cache[str(p)] = (mtime, cfg)
    return cfg


def with_overrides(cfg: SegmentConfig, **changes: Any) -> SegmentConfig:
    """A validated copy with some top-level fields replaced (CLI overrides)."""
    return config_from_dict(config_to_dict(replace(cfg, **changes)))


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


def frame_usable(analysis_metadata: Any) -> bool:
    """False only when the frame-quality pass marked the frame unusable
    (``analysis_metadata.frame_quality.usable`` is false). A missing key —
    every frame analysed before that pass existed — means usable.
    """
    if not isinstance(analysis_metadata, Mapping):
        return True
    quality = analysis_metadata.get("frame_quality")
    if not isinstance(quality, Mapping):
        return True
    usable = quality.get("usable")
    if isinstance(usable, str):       # value extracted as JSON text in SQL
        return usable.strip().lower() != "false"
    return usable is not False


def frame_score(dino_rqi_score: Any, analysis_metadata: Any) -> Optional[float]:
    """Continuous score of one frame: metadata ``dino_score`` → ``dino_rqi_score``."""
    if isinstance(analysis_metadata, Mapping):
        continuous = _finite(analysis_metadata.get("dino_score"))
        if continuous is not None:
            return continuous
    return _finite(dino_rqi_score)


def frame_p_bad(dino_rqi_score: Any, analysis_metadata: Any, scale: RqiScale) -> Optional[float]:
    """P(bad) of one frame: calibrated ``dino_p_bad`` when the frame has it,
    otherwise a hard 0/1 from the ordinal class, so a segment's mean degrades
    gracefully to "share of bad frames" for older analyses.
    """
    if isinstance(analysis_metadata, Mapping):
        p = _finite(analysis_metadata.get("dino_p_bad"))
        if p is not None:
            return max(0.0, min(1.0, p))
    rqi = _finite(dino_rqi_score)
    if rqi is None:
        return None
    return 1.0 if scale.is_bad(rqi) else 0.0


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


def threshold_margin(score: float, thresholds: Sequence[float]) -> float:
    """Distance of a score from the nearest class boundary."""
    return min(abs(score - t) for t in thresholds)


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------

def count_factor(n: int, c: ConfidenceConfig) -> float:
    return 1.0 - math.exp(-n / c.n_ref) if n > 0 else 0.0


def spread_factor(spread_iqr: float, c: ConfidenceConfig) -> float:
    return math.exp(-((spread_iqr / c.spread_ref) ** 2))


def margin_factor(margin: float, c: ConfidenceConfig) -> float:
    return 0.5 + 0.5 * min(1.0, margin / c.margin_ref)


def base_confidence(n: int, spread_iqr: float, margin: float, c: ConfidenceConfig) -> float:
    """Confidence before the age factor (see the module docstring)."""
    if n <= 0:
        return 0.0
    value = count_factor(n, c) * spread_factor(spread_iqr, c) * margin_factor(margin, c)
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


def unlabelled_cap(cfg: SegmentConfig) -> float:
    """The highest confidence that still reads as ``unlabelled_area.cap_level``."""
    edge = (cfg.confidence.high if cfg.unlabelled_area.cap_level == LEVEL_MEDIUM
            else cfg.confidence.medium)
    return max(0.0, math.nextafter(edge, 0.0))


def apply_unlabelled_area(
    confidence: float, label_nearby: bool, cfg: SegmentConfig
) -> tuple[float, bool]:
    """(confidence, capped). Capped only when the rule is on, no human label
    is within ``radius_km`` and the cap actually LOWERS the confidence."""
    if cfg.unlabelled_area.radius_km <= 0 or label_nearby:
        return confidence, False
    cap = unlabelled_cap(cfg)
    if confidence > cap:
        return cap, True
    return confidence, False


def confidence_level(confidence: float, n_images: int, cfg: SegmentConfig) -> str:
    """"high" | "medium" | "low"; below ``min_images`` it is always "low"."""
    if n_images < cfg.min_images:
        return LEVEL_LOW
    if confidence >= cfg.confidence.high:
        return LEVEL_HIGH
    if confidence >= cfg.confidence.medium:
        return LEVEL_MEDIUM
    return LEVEL_LOW


def confidence_reason(
    confidence: float,
    n_images: int,
    score: Optional[float],
    newest_capture: Optional[dt.date],
    built_on: dt.date,
    cfg: SegmentConfig,
    unlabelled_area: bool = False,
) -> Optional[str]:
    """Why the confidence is not high: the factor of the formula that pulls it
    down the most. None for a "high" segment (nothing to explain).

    Works from what a stored segment carries. The spread (IQR) of the frame
    scores is not stored, but the confidence is the product of the four
    factors, so the spread factor is what remains after dividing out the other
    three. ``built_on`` is the day the confidence was computed (the age factor
    is evaluated as of that day). ``unlabelled_area`` = the stored flag that
    the unlabelled-area cap lowered this segment's confidence; then the cap is
    what limits it.
    """
    if n_images <= 0 or score is None:
        return REASON_FEW_IMAGES
    if confidence_level(confidence, n_images, cfg) == LEVEL_HIGH:
        return None
    if n_images < cfg.min_images:
        return REASON_FEW_IMAGES
    if unlabelled_area:
        return REASON_UNLABELLED_AREA
    factors = {
        REASON_FEW_IMAGES: count_factor(n_images, cfg.confidence),
        REASON_NEAR_THRESHOLD: margin_factor(
            threshold_margin(score, cfg.thresholds), cfg.confidence),
        REASON_OLD_IMAGES: age_factor(newest_capture, built_on, cfg.age),
    }
    known = math.prod(factors.values())
    factors[REASON_DISAGREEMENT] = min(1.0, confidence / known) if known > 0 else 1.0
    # Smallest factor wins; the fixed order below settles exact ties.
    order = (REASON_FEW_IMAGES, REASON_DISAGREEMENT, REASON_NEAR_THRESHOLD, REASON_OLD_IMAGES)
    return min(order, key=lambda reason: (factors[reason], order.index(reason)))


# --------------------------------------------------------------------------
# The aggregate
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SegmentAggregate:
    n_images: int
    score: Optional[float]      # aggregated continuous score
    rqi: Optional[int]          # class label, None without frames
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
    rqi = cfg.classify(score)

    p_values = [f.p_bad for f in frames if f.p_bad is not None]
    p_bad = mean(p_values) if p_values else None

    if cfg.aggregator == "mean_p_bad" and p_bad is not None:
        # P(bad) decides which side of the good/bad boundary the segment is on;
        # the median score only picks the class within that side.
        rqi = cfg.scale.gate(rqi, bad=p_bad >= cfg.p_bad_threshold)

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
