"""Aggregators, the RQI scale helper, confidence, age factor, config loading."""
import datetime as dt
import json
import math
import os

import pytest

from app.services.segment_aggregation import (
    CONFIG_PATH,
    AgeConfig,
    ConfidenceConfig,
    FrameObs,
    RqiScale,
    age_factor,
    age_years,
    aggregate_frames,
    base_confidence,
    confidence_level,
    confidence_reason,
    config_from_dict,
    config_to_dict,
    frame_p_bad,
    frame_score,
    frame_usable,
    iqr,
    load_config,
    median,
    percentile,
    threshold_margin,
    trimmed_mean,
    with_overrides,
)
from geo_helpers import BASE_CONFIG, FLIPPED_CONFIG, make_config

TODAY = dt.date(2026, 11, 26)
CFG = make_config()
FLIPPED = config_from_dict(FLIPPED_CONFIG)
SCALE = CFG.scale


def frames(scores, p_bad=None, capture=None):
    return [FrameObs(s, p_bad, capture) for s in scores]


# ---- config ---------------------------------------------------------------

def test_shipped_config_is_valid_and_states_the_scale_explicitly():
    cfg = load_config()
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config_from_dict(data) == cfg
    # The scale is stated in the file — never implied by code. (No class
    # labels or cut points are pinned here on purpose: flipping the scale is
    # an edit of the JSON alone and must not need a test change.)
    assert set(data["scale"]) == {"classes", "higher_is_worse", "bad_class"}
    assert len(cfg.thresholds) == len(cfg.scale.classes) - 1 == 3
    # Scale-independent part of the ML recipe (ml/segment_recipe.json).
    assert cfg.segment_length_m == 200
    assert cfg.aggregator == "median_score"
    assert (cfg.p_bad_threshold, cfg.min_images) == (0.5, 2)
    assert cfg.confidence == ConfidenceConfig(0.5, 2.0, 0.6, 0.8, 0.55)
    assert cfg.age == AgeConfig(3, 5)


def test_scale_and_thresholds_are_required():
    without_scale = {k: v for k, v in BASE_CONFIG.items() if k != "scale"}
    with pytest.raises(ValueError, match="scale"):
        config_from_dict(without_scale)
    without_thresholds = {k: v for k, v in BASE_CONFIG.items() if k != "thresholds"}
    with pytest.raises(ValueError, match="thresholds"):
        config_from_dict(without_thresholds)


def test_other_missing_keys_fall_back_and_unknown_keys_are_ignored():
    cfg = config_from_dict({
        "thresholds": [1.5, 2.5, 3.5], "scale": BASE_CONFIG["scale"],
        "segment_length_m": 200, "confidence": {"n_ref": 4}, "future": 1,
    })
    assert cfg.segment_length_m == 200
    assert cfg.confidence.n_ref == 4
    assert cfg.confidence.spread_ref == ConfidenceConfig().spread_ref
    assert cfg.aggregator == "median_score"


@pytest.mark.parametrize(
    "bad",
    [
        {"aggregator": "mode"},
        {"segment_length_m": 0},
        {"thresholds": [1.5, 2.5]},                       # 4 classes need 3 cut points
        {"thresholds": [2.5, 1.5, 3.2]},
        {"trim_fraction": 0.5},
        {"p_bad_threshold": 1.2},
        {"min_images": 0},
        {"confidence": {"n_ref": 0}},
        {"confidence": {"high": 0.2, "medium": 0.5}},
        {"age": {"half_life_years": 0}},
        {"confidence": "high"},
        {"segment_length_m": "long"},
        {"scale": {"classes": [1, 2, 3, 4], "higher_is_worse": True}},            # no bad_class
        {"scale": {"classes": [1, 2, 3, 4], "higher_is_worse": "yes", "bad_class": 3}},
        {"scale": {"classes": [4, 3, 2, 1], "higher_is_worse": True, "bad_class": 3}},
        {"scale": {"classes": [1, 2, 3, 4], "higher_is_worse": True, "bad_class": 7}},
        {"scale": {"classes": [1, 2, 3, 4], "higher_is_worse": True, "bad_class": 1}},   # all bad
        {"scale": {"classes": [2, 3, 4, 5], "higher_is_worse": False, "bad_class": 5}},  # all bad
    ],
)
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ValueError):
        config_from_dict({**BASE_CONFIG, **bad})


def test_load_config_missing_or_broken_file_is_an_error_and_reloads_on_change(tmp_path):
    path = tmp_path / "segment_aggregation.json"
    with pytest.raises(ValueError, match="not found"):
        load_config(path)                 # nothing safe to fall back to

    path.write_text(json.dumps({**BASE_CONFIG, "segment_length_m": 100}))
    assert load_config(path).segment_length_m == 100

    path.write_text(json.dumps({**BASE_CONFIG, "segment_length_m": 250}))
    os.utime(path, (1_900_000_000, 1_900_000_000))   # force a different mtime
    assert load_config(path).segment_length_m == 250

    path.write_text("{not json")
    os.utime(path, (1_900_000_100, 1_900_000_100))
    with pytest.raises(ValueError, match="not valid JSON"):
        load_config(path)


def test_config_round_trip_and_overrides():
    assert config_from_dict(config_to_dict(CFG)) == CFG
    assert config_from_dict(config_to_dict(FLIPPED)) == FLIPPED
    assert with_overrides(CFG, aggregator="mean_score").aggregator == "mean_score"
    assert with_overrides(CFG, segment_length_m=80).confidence == CFG.confidence
    with pytest.raises(ValueError):
        with_overrides(CFG, segment_length_m=-1)


# ---- the scale helper -----------------------------------------------------

@pytest.mark.parametrize(
    "score, expected",
    [(1.0, 1), (1.50, 1), (1.51, 2), (2.0, 2), (2.469, 2), (2.47, 3), (3.0, 3),
     (3.179, 3), (3.18, 4), (4.0, 4)],
)
def test_classify_through_thresholds(score, expected):
    assert CFG.classify(score) == expected


def test_scale_today_higher_is_worse():
    assert SCALE.best_to_worst == (1, 2, 3, 4)
    assert SCALE.ascending == (1, 2, 3, 4)
    assert [SCALE.is_bad(c) for c in (1, 2, 3, 4)] == [False, False, True, True]
    assert SCALE.is_bad(2.5) is False and SCALE.is_bad(3.5) is True       # half-step labels
    assert SCALE.badness(3.4) > SCALE.badness(1.2)
    # gate: only moves a class that is on the wrong side of the boundary
    assert [SCALE.gate(c, bad=True) for c in (1, 2, 3, 4)] == [3, 3, 3, 4]
    assert [SCALE.gate(c, bad=False) for c in (1, 2, 3, 4)] == [1, 2, 2, 2]


def test_scale_flipped_five_is_excellent():
    scale = FLIPPED.scale
    assert scale.best_to_worst == (5, 4, 3, 2)
    assert scale.ascending == (2, 3, 4, 5)
    assert [scale.is_bad(c) for c in (2, 3, 4, 5)] == [True, True, False, False]
    assert scale.badness(2.6) > scale.badness(4.8)                        # low score = worse
    assert [scale.gate(c, bad=True) for c in (5, 4, 3, 2)] == [3, 3, 3, 2]
    assert [scale.gate(c, bad=False) for c in (5, 4, 3, 2)] == [5, 4, 4, 4]


@pytest.mark.parametrize("score", [1.0, 1.3, 1.51, 1.9, 2.47, 2.8, 3.18, 3.6, 4.0])
def test_flipping_the_config_mirrors_every_class(score):
    # x → 6 − x on the data + the mirrored config must give the mirrored class,
    # including for a score sitting exactly on a threshold (worse side wins).
    assert FLIPPED.classify(6 - score) == 6 - CFG.classify(score)


def test_flipping_the_config_mirrors_a_whole_aggregate():
    obs = [FrameObs(2.3, 0.7, dt.date(2020, 5, 1)), FrameObs(2.6, 0.8), FrameObs(3.4, 0.6),
           FrameObs(2.2, 0.9), FrameObs(1.9, 0.4)]
    mirrored = [FrameObs(6 - f.score, f.p_bad, f.capture_date) for f in obs]
    for aggregator in ("median_score", "mean_score", "trimmed_mean_score", "mean_p_bad"):
        a = aggregate_frames(obs, with_overrides(CFG, aggregator=aggregator), TODAY)
        b = aggregate_frames(mirrored, with_overrides(FLIPPED, aggregator=aggregator), TODAY)
        assert b.rqi == 6 - a.rqi, aggregator
        assert b.score == pytest.approx(6 - a.score)
        assert b.p_bad == pytest.approx(a.p_bad)
        assert b.confidence == pytest.approx(a.confidence)


def test_scale_is_frozen_and_comparable():
    assert RqiScale((1, 2, 3, 4), True, 3) == SCALE
    with pytest.raises(Exception):
        SCALE.bad_class = 2


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
    assert frame_p_bad(2.0, {"dino_p_bad": 0.83}, SCALE) == 0.83
    assert frame_p_bad(2.0, {"dino_p_bad": 1.7}, SCALE) == 1.0    # clamped
    assert frame_p_bad(3.0, None, SCALE) == 1.0                    # class 3 is bad today
    assert frame_p_bad(4.0, {}, SCALE) == 1.0
    assert frame_p_bad(2.0, None, SCALE) == 0.0
    assert frame_p_bad(None, None, SCALE) is None
    # …and follows the scale when it is flipped (5 = excellent).
    assert frame_p_bad(2.0, None, FLIPPED.scale) == 1.0
    assert frame_p_bad(3.0, None, FLIPPED.scale) == 1.0
    assert frame_p_bad(4.0, None, FLIPPED.scale) == 0.0


def test_frame_usable_only_rejects_an_explicit_false():
    # No frame-quality pass yet → everything is usable (the filter is a no-op).
    assert frame_usable(None)
    assert frame_usable({})
    assert frame_usable({"dino_score": 2.0})
    assert frame_usable({"frame_quality": None})
    assert frame_usable({"frame_quality": {}})
    assert frame_usable({"frame_quality": {"usable": None}})
    assert frame_usable({"frame_quality": {"usable": True}})
    assert frame_usable({"frame_quality": {"usable": "true"}})
    assert frame_usable({"frame_quality": "blurry"})              # unexpected shape
    # Marked unusable → skipped, as a JSON bool or as text extracted in SQL.
    assert not frame_usable({"frame_quality": {"usable": False}})
    assert not frame_usable({"frame_quality": {"usable": "false"}})
    assert not frame_usable({"frame_quality": {"usable": "False", "reason": "occluded"}})


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
    assert agg.score == 2.0
    assert agg.rqi == 2


def test_mean_score_aggregator():
    agg = aggregate_frames(frames(SKEWED + [4.0]), with_overrides(CFG, aggregator="mean_score"), TODAY)
    assert agg.score == pytest.approx(16 / 6)
    assert agg.rqi == 3


def test_trimmed_mean_score_aggregator():
    cfg = with_overrides(CFG, aggregator="trimmed_mean_score", trim_fraction=0.2)
    agg = aggregate_frames(frames(SKEWED), cfg, TODAY)     # drops one 2.0 and the 4.0
    assert agg.score == 2.0
    assert agg.rqi == 2


def test_mean_p_bad_gates_the_bad_boundary():
    cfg = with_overrides(CFG, aggregator="mean_p_bad")
    # Median score says "good" (class 2) but the frames are mostly judged bad.
    bad = aggregate_frames([FrameObs(2.3, 0.7), FrameObs(2.4, 0.8), FrameObs(2.2, 0.6)], cfg, TODAY)
    assert bad.score == 2.3
    assert bad.p_bad == pytest.approx(0.7)
    assert bad.rqi == 3
    # Median score says "bad" (class 3) but P(bad) is low → capped at 2.
    good = aggregate_frames([FrameObs(2.6, 0.2), FrameObs(2.5, 0.3), FrameObs(2.7, 0.1)], cfg, TODAY)
    assert good.rqi == 2
    # A clear class 4 stays 4; a clear class 1 stays 1.
    assert aggregate_frames(frames([3.6, 3.7, 3.8], p_bad=0.95), cfg, TODAY).rqi == 4
    assert aggregate_frames(frames([1.1, 1.2, 1.0], p_bad=0.02), cfg, TODAY).rqi == 1
    # Without any P(bad) the gate cannot apply: plain median class.
    assert aggregate_frames(frames([2.6, 2.5, 2.7]), cfg, TODAY).rqi == 3


def test_p_bad_is_reported_for_every_aggregator():
    agg = aggregate_frames([FrameObs(2.0, 0.1), FrameObs(2.0, 0.3), FrameObs(2.0, None)], CFG, TODAY)
    assert agg.p_bad == pytest.approx(0.2)      # mean of the known values
    assert agg.rqi == 2                           # ...and it does not gate median_score


def test_empty_segment_has_no_class():
    agg = aggregate_frames([], CFG, TODAY)
    assert (agg.n_images, agg.score, agg.rqi, agg.p_bad, agg.confidence) == (0, None, None, None, 0.0)
    assert agg.capture_date_min is None and agg.capture_date_max is None
    assert confidence_level(agg.confidence, agg.n_images, CFG) == "low"


# ---- confidence -----------------------------------------------------------

def test_base_confidence_formula():
    c = CFG.confidence                                # n_ref 8, spread 0.6, margin 0.3
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
    c = CFG.confidence
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
    mixed = [FrameObs(2.0, None, dt.date(2012, 5, 1))] * 7 + [FrameObs(2.0, None, dt.date(2025, 1, 1))]
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
    assert agg.score == pytest.approx(2.5)
    assert agg.rqi == 3
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
    assert agg.rqi == 4
    assert agg.n_images == 2
    assert confidence_level(agg.confidence, agg.n_images, CFG) == "low"


# ---- confidence reason ----------------------------------------------------

def reason_for(obs, cfg=CFG):
    """Aggregate, then explain from what a stored row would carry."""
    agg = aggregate_frames(obs, cfg, TODAY)
    return confidence_reason(agg.confidence, agg.n_images, agg.score, agg.capture_date_max, TODAY, cfg)


def test_reason_is_none_when_confidence_is_high():
    assert reason_for(frames([2.0] * 30)) is None


def test_reason_few_images():
    assert reason_for(frames([2.0, 2.0])) == "few_images"            # below min_images
    assert reason_for(frames([2.0] * 4)) == "few_images"             # allowed, but thin
    assert confidence_reason(0.0, 0, None, None, TODAY, CFG) == "few_images"


def test_reason_disagreement():
    # Many frames, far from a threshold, recent — but they disagree wildly.
    obs = frames([1.0] * 10 + [2.0] * 10 + [3.0] * 10, capture=dt.date(2026, 1, 1))
    assert reason_for(obs) == "disagreement"


def test_reason_near_threshold():
    # Many agreeing, recent frames whose score sits right on the 2.47 cut.
    obs = frames([2.47] * 60, capture=dt.date(2026, 1, 1))
    assert reason_for(obs) == "near_threshold"


def test_reason_old_images():
    # Many agreeing frames, clear class — but 15 years old.
    obs = frames([2.0] * 60, capture=dt.date(2011, 11, 1))
    assert reason_for(obs) == "old_images"


def test_reason_names_the_single_factor_that_was_pushed_down():
    """Property check against the formula: start from an ideal segment and
    degrade exactly one factor at a time."""
    ideal = dict(n=200, spread=0.0, score=2.0, capture=dt.date(2026, 1, 1))

    def explain(n, spread, score, capture):
        conf = (
            base_confidence(n, spread, threshold_margin(score, CFG.thresholds), CFG.confidence)
            * age_factor(capture, TODAY, CFG.age)
        )
        return confidence_reason(conf, n, score, capture, TODAY, CFG)

    assert explain(**ideal) is None
    assert explain(**{**ideal, "n": 3}) == "few_images"
    assert explain(**{**ideal, "spread": 1.2}) == "disagreement"
    assert explain(**{**ideal, "score": 2.48}) == "near_threshold"
    assert explain(**{**ideal, "capture": dt.date(2005, 1, 1)}) == "old_images"
