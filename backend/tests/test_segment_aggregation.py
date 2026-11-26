"""Aggregators, classification, confidence, age factor and config loading."""
import datetime as dt
import json
import math

import pytest

from app.core.rqi_scale import SCALE
from app.services.segment_aggregation import (
    CONFIG_PATH,
    DEFAULT_CONFIG,
    AgeConfig,
    ConfidenceConfig,
    FrameObs,
    age_factor,
    age_years,
    aggregate_frames,
    base_confidence,
    classify,
    confidence_level,
    config_from_dict,
    frame_p_bad,
    frame_score,
    iqr,
    load_config,
    median,
    percentile,
    threshold_margin,
    trimmed_mean,
    with_overrides,
)

TODAY = dt.date(2026, 11, 26)
CFG = DEFAULT_CONFIG


# Frame scores and expected classes are written in SEVERITY (1 = Kiváló … 4 =
# Rossz, the numbering the thresholds are tuned in); sv() maps them onto the
# canonical scale the module reads and returns, so the tests hold either way.
sv = SCALE.from_severity


def obs(score, p_bad=None, capture=None):
    return FrameObs(sv(score), p_bad, capture)


def frames(scores, p_bad=None, capture=None):
    return [obs(s, p_bad, capture) for s in scores]


# ---- config ---------------------------------------------------------------

def test_shipped_config_file_equals_the_documented_defaults():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert data == {
        "version": 1, "segment_length_m": 150, "aggregator": "median_score",
        "trim_fraction": 0.1, "scale_direction": "lower_is_better",
        "thresholds": [1.51, 2.47, 3.18],
        "p_bad_threshold": 0.5, "min_images": 3,
        "confidence": {"n_ref": 8, "spread_ref": 0.6, "margin_ref": 0.3,
                       "high": 0.66, "medium": 0.33},
        "age": {"grace_years": 3, "half_life_years": 5},
    }
    assert config_from_dict(data) == DEFAULT_CONFIG
    assert load_config() == DEFAULT_CONFIG


def test_missing_keys_fall_back_and_unknown_keys_are_ignored():
    cfg = config_from_dict({"segment_length_m": 200, "confidence": {"n_ref": 4}, "future": 1})
    assert cfg.segment_length_m == 200
    assert cfg.confidence.n_ref == 4
    assert cfg.confidence.spread_ref == DEFAULT_CONFIG.confidence.spread_ref
    assert cfg.thresholds == DEFAULT_CONFIG.thresholds


@pytest.mark.parametrize(
    "bad",
    [
        {"aggregator": "mode"},
        {"segment_length_m": 0},
        {"thresholds": [1.5, 2.5]},
        {"thresholds": [2.5, 1.5, 3.2]},
        {"trim_fraction": 0.5},
        {"p_bad_threshold": 1.2},
        {"min_images": 0},
        {"confidence": {"n_ref": 0}},
        {"confidence": {"high": 0.2, "medium": 0.5}},
        {"age": {"half_life_years": 0}},
        {"confidence": "high"},
        {"segment_length_m": "long"},
    ],
)
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ValueError):
        config_from_dict(bad)


def test_load_config_missing_file_uses_defaults_and_reload_on_change(tmp_path):
    path = tmp_path / "segment_aggregation.json"
    assert load_config(path) == DEFAULT_CONFIG

    path.write_text(json.dumps({"segment_length_m": 100}))
    assert load_config(path).segment_length_m == 100

    path.write_text(json.dumps({"segment_length_m": 250}))
    import os
    os.utime(path, (1_900_000_000, 1_900_000_000))   # force a different mtime
    assert load_config(path).segment_length_m == 250

    path.write_text("{not json")
    os.utime(path, (1_900_000_100, 1_900_000_100))
    with pytest.raises(ValueError):
        load_config(path)


def test_with_overrides_validates():
    assert with_overrides(CFG, aggregator="mean_score").aggregator == "mean_score"
    assert with_overrides(CFG, segment_length_m=80).confidence == CFG.confidence
    with pytest.raises(ValueError):
        with_overrides(CFG, segment_length_m=-1)


# ---- per-frame inputs -----------------------------------------------------

def test_frame_score_prefers_the_continuous_estimate():
    assert frame_score(3.0, {"dino_score": 2.61}) == 2.61
    assert frame_score(3.0, {"dino_score": "2.61"}) == 2.61      # JSON text from SQL
    assert frame_score(3.0, {"dino_score": None}) == 3.0
    assert frame_score(3.0, {"other": 1}) == 3.0
    assert frame_score(3.0, None) == 3.0
    assert frame_score(None, None) is None
    assert frame_score(None, {"dino_score": "nan"}) is None
    assert frame_score(2.0, {"dino_score": "garbage"}) == 2.0


def test_frame_p_bad_falls_back_to_the_ordinal_class():
    assert frame_p_bad(2.0, {"dino_p_bad": 0.83}) == 0.83
    assert frame_p_bad(2.0, {"dino_p_bad": 1.7}) == 1.0          # clamped
    assert frame_p_bad(sv(3.0), None) == 1.0                      # Közepes or worse is bad
    assert frame_p_bad(sv(4.0), {}) == 1.0
    assert frame_p_bad(sv(2.0), None) == 0.0
    assert frame_p_bad(None, None) is None


# ---- statistics -----------------------------------------------------------

def test_percentile_linear_interpolation():
    data = [1.0, 2.0, 3.0, 4.0]
    assert percentile(data, 0.0) == 1.0
    assert percentile(data, 1.0) == 4.0
    assert percentile(data, 0.5) == 2.5
    assert percentile(data, 0.25) == 1.75
    assert percentile([7.0], 0.9) == 7.0
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_median_and_iqr():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 2, 3]) == 2.5
    assert iqr([1, 2, 3, 4]) == pytest.approx(1.5)
    assert iqr([2.2]) == 0.0
    assert iqr([2, 2, 2, 2]) == 0.0


def test_trimmed_mean_drops_from_both_ends():
    values = [1, 2, 2, 2, 2, 2, 2, 2, 2, 4]          # n=10, 10 % → drop one each end
    assert trimmed_mean(values, 0.1) == 2.0
    assert trimmed_mean(values, 0.0) == pytest.approx(2.1)
    assert trimmed_mean([1, 4], 0.1) == 2.5            # too few to trim anything


@pytest.mark.parametrize(
    "score, expected",
    [(1.0, 1), (1.50, 1), (1.51, 2), (2.0, 2), (2.469, 2), (2.47, 3), (3.0, 3),
     (3.179, 3), (3.18, 4), (4.0, 4)],
)
def test_classify_through_thresholds(score, expected):
    assert classify(score, CFG.thresholds) == expected


def test_threshold_margin_is_distance_to_the_nearest_boundary():
    assert threshold_margin(2.0, CFG.thresholds) == pytest.approx(0.47)
    assert threshold_margin(2.47, CFG.thresholds) == 0.0
    assert threshold_margin(4.0, CFG.thresholds) == pytest.approx(0.82)
    assert threshold_margin(1.0, CFG.thresholds) == pytest.approx(0.51)


# ---- aggregators ----------------------------------------------------------

SKEWED = [2.0, 2.0, 2.0, 2.0, 4.0]      # median 2.0, mean 2.4, one outlier


def test_median_score_aggregator():
    agg = aggregate_frames(frames(SKEWED), CFG, TODAY)
    assert agg.n_images == 5
    assert agg.score == pytest.approx(sv(2.0))
    assert agg.rqi == sv(2)


def test_mean_score_aggregator():
    agg = aggregate_frames(frames(SKEWED + [4.0]), with_overrides(CFG, aggregator="mean_score"), TODAY)
    assert agg.score == pytest.approx(sv(16 / 6))
    assert agg.rqi == sv(3)


def test_trimmed_mean_score_aggregator():
    cfg = with_overrides(CFG, aggregator="trimmed_mean_score", trim_fraction=0.2)
    agg = aggregate_frames(frames(SKEWED), cfg, TODAY)     # drops one 2.0 and the 4.0
    assert agg.score == pytest.approx(sv(2.0))
    assert agg.rqi == sv(2)


def test_mean_p_bad_gates_the_bad_boundary():
    cfg = with_overrides(CFG, aggregator="mean_p_bad")
    # Median score says "good" (class 2) but the frames are mostly judged bad.
    bad = aggregate_frames([obs(2.3, 0.7), obs(2.4, 0.8), obs(2.2, 0.6)], cfg, TODAY)
    assert bad.score == pytest.approx(sv(2.3))
    assert bad.p_bad == pytest.approx(0.7)
    assert bad.rqi == sv(3)
    # Median score says "bad" (class 3) but P(bad) is low → capped at 2.
    good = aggregate_frames([obs(2.6, 0.2), obs(2.5, 0.3), obs(2.7, 0.1)], cfg, TODAY)
    assert good.rqi == sv(2)
    # A clear class 4 stays 4; a clear class 1 stays 1.
    assert aggregate_frames(frames([3.6, 3.7, 3.8], p_bad=0.95), cfg, TODAY).rqi == sv(4)
    assert aggregate_frames(frames([1.1, 1.2, 1.0], p_bad=0.02), cfg, TODAY).rqi == sv(1)
    # Without any P(bad) the gate cannot apply: plain median class.
    assert aggregate_frames(frames([2.6, 2.5, 2.7]), cfg, TODAY).rqi == sv(3)


def test_p_bad_is_reported_for_every_aggregator():
    agg = aggregate_frames([obs(2.0, 0.1), obs(2.0, 0.3), obs(2.0, None)], CFG, TODAY)
    assert agg.p_bad == pytest.approx(0.2)      # mean of the known values
    assert agg.rqi == sv(2)                           # ...and it does not gate median_score


def test_empty_segment_has_no_class():
    agg = aggregate_frames([], CFG, TODAY)
    assert (agg.n_images, agg.score, agg.rqi, agg.p_bad, agg.confidence) == (0, None, None, None, 0.0)
    assert agg.capture_date_min is None and agg.capture_date_max is None
    assert confidence_level(agg.confidence, agg.n_images, CFG) == "low"


# ---- confidence -----------------------------------------------------------

def test_base_confidence_formula():
    c = ConfidenceConfig()
    # n=8, no spread, far from a threshold → 1 - e^-1
    assert base_confidence(8, 0.0, 0.5, c) == pytest.approx(1 - math.exp(-1))
    # each factor on its own
    assert base_confidence(8, 0.6, 0.5, c) == pytest.approx((1 - math.exp(-1)) * math.exp(-1))
    assert base_confidence(8, 0.0, 0.0, c) == pytest.approx((1 - math.exp(-1)) * 0.5)
    assert base_confidence(8, 0.0, 0.15, c) == pytest.approx((1 - math.exp(-1)) * 0.75)
    assert base_confidence(16, 0.3, 0.1, c) == pytest.approx(
        (1 - math.exp(-2)) * math.exp(-0.25) * (0.5 + 0.5 * (0.1 / 0.3))
    )
    assert base_confidence(0, 0.0, 1.0, c) == 0.0


def test_base_confidence_is_monotone():
    c = ConfidenceConfig()
    by_n = [base_confidence(n, 0.2, 0.2, c) for n in range(1, 40)]
    assert all(a < b for a, b in zip(by_n, by_n[1:]))
    by_spread = [base_confidence(10, s / 10, 0.2, c) for s in range(0, 20)]
    assert all(a > b for a, b in zip(by_spread, by_spread[1:]))
    assert base_confidence(10, 0.2, 0.3, c) == base_confidence(10, 0.2, 3.0, c)   # margin saturates
    assert 0.0 <= base_confidence(10_000, 0.0, 9.0, c) <= 1.0


def test_age_years_month_precision():
    assert age_years(dt.date(2023, 11, 1), TODAY) == 3.0
    assert age_years(dt.date(2026, 5, 1), TODAY) == 0.5
    assert age_years(dt.date(2027, 3, 1), TODAY) == 0.0      # future date never negative
    assert age_years(None, TODAY) is None


def test_age_factor():
    a = AgeConfig()                                             # grace 3 y, half-life 5 y
    assert age_factor(None, TODAY, a) == 1.0                   # unknown → no penalty
    assert age_factor(dt.date(2025, 6, 1), TODAY, a) == 1.0    # within the grace period
    assert age_factor(dt.date(2023, 11, 1), TODAY, a) == 1.0   # exactly 3 years
    assert age_factor(dt.date(2018, 11, 1), TODAY, a) == pytest.approx(0.5)    # 8 y = grace + 1 half-life
    assert age_factor(dt.date(2013, 11, 1), TODAY, a) == pytest.approx(0.25)
    assert age_factor(dt.date(2021, 5, 1), TODAY, a) == pytest.approx(0.5 ** (2.5 / 5))


def test_confidence_uses_the_newest_capture_date():
    scores = [2.0] * 8
    fresh = aggregate_frames(frames(scores, capture=dt.date(2025, 6, 1)), CFG, TODAY)
    unknown = aggregate_frames(frames(scores), CFG, TODAY)
    assert fresh.confidence == pytest.approx(unknown.confidence)
    assert fresh.confidence == pytest.approx(1 - math.exp(-1))

    old = aggregate_frames(frames(scores, capture=dt.date(2018, 11, 1)), CFG, TODAY)
    assert old.confidence == pytest.approx(0.5 * (1 - math.exp(-1)))

    # One recent pass over an otherwise old segment: the NEWEST date counts.
    mixed = [obs(2.0, None, dt.date(2012, 5, 1))] * 7 + [obs(2.0, None, dt.date(2025, 1, 1))]
    agg = aggregate_frames(mixed, CFG, TODAY)
    assert agg.confidence == pytest.approx(fresh.confidence)
    assert agg.capture_date_min == dt.date(2012, 5, 1)
    assert agg.capture_date_max == dt.date(2025, 1, 1)


def test_confidence_full_formula_on_a_spread_segment():
    scores = [2.0, 2.2, 2.4, 2.6, 2.8, 3.0]         # median 2.5, IQR 0.5
    agg = aggregate_frames(frames(scores), CFG, TODAY)
    expected = (
        (1 - math.exp(-6 / 8))
        * math.exp(-((0.5 / 0.6) ** 2))
        * (0.5 + 0.5 * min(1.0, 0.03 / 0.3))         # 0.03 from the 2.47 boundary
    )
    assert agg.score == pytest.approx(sv(2.5))
    assert agg.rqi == sv(3)
    assert agg.confidence == pytest.approx(expected)


def test_confidence_level_bands_and_min_images():
    assert confidence_level(0.66, 10, CFG) == "high"
    assert confidence_level(0.6599, 10, CFG) == "medium"
    assert confidence_level(0.33, 10, CFG) == "medium"
    assert confidence_level(0.3299, 10, CFG) == "low"
    # Below min_images the level is "low" whatever the number says.
    assert confidence_level(0.99, 2, CFG) == "low"
    assert confidence_level(0.99, 3, CFG) == "high"


def test_segment_below_min_images_still_gets_a_class():
    agg = aggregate_frames(frames([3.5, 3.6]), CFG, TODAY)
    assert agg.rqi == sv(4)
    assert agg.n_images == 2
    assert confidence_level(agg.confidence, agg.n_images, CFG) == "low"
