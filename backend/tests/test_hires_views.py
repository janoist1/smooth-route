"""Unit tests for the hi-res RQI view helpers (no torch needed).

Spec parsing/validation is pure Python and runs everywhere; the numeric
tests need numpy + Pillow (dev machine) and are skipped in the minimal CI env.
"""
import pytest

from app.services.hires_views import (IMAGENET_MEAN, IMAGENET_STD,
                                      needed_views, pool_tokens, preprocess,
                                      road_mask, split_key,
                                      validate_hires_recipe)

try:  # numeric helpers need numpy + Pillow (absent in the minimal CI env)
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover - CI path
    np = Image = None
needs_numpy = pytest.mark.skipif(np is None, reason="numpy/Pillow not installed")

FULL = {"box": [0.0, 0.0, 1.0, 1.0], "size": [588, 392], "mid_layer": 8,
        "road_y": 0.5}


def recipe(keys, views=None):
    return {"name": "t", "keys": keys,
            "hires_views": {"full": dict(FULL)} if views is None else views}


# --- spec parsing / validation (pure Python) --------------------------------

def test_split_key_only_matches_declared_views():
    views = {"full": FULL}
    assert split_key("full_midmean", views) == ("full", "midmean")
    assert split_key("cls", views) is None
    assert split_key("patch_crop", views) is None   # classic 224-px key
    assert split_key("road50_mean", views) is None  # view not declared


def test_needed_views_groups_pools_per_view():
    r = recipe(["cls", "patch", "full_midmean", "full_midstd"])
    assert needed_views(r) == {"full": {"midmean", "midstd"}}
    assert needed_views({"keys": ["cls", "patch"]}) == {}


def test_validate_accepts_candidate_recipe():
    validate_hires_recipe(recipe(["cls", "patch", "full_midmean", "full_midstd"]))
    validate_hires_recipe({"keys": ["cls", "patch"]})  # classic recipe: no-op


def test_validate_rejects_unknown_pool():
    with pytest.raises(ValueError, match="unknown pool"):
        validate_hires_recipe(recipe(["cls", "full_sp"]))


def test_validate_rejects_size_not_multiple_of_patch():
    with pytest.raises(ValueError, match="multiple"):
        validate_hires_recipe(recipe(["full_mean"],
                                     {"full": dict(FULL, size=[600, 400])}))


def test_validate_rejects_missing_spec_field_and_bad_box():
    spec = dict(FULL)
    del spec["road_y"]
    with pytest.raises(ValueError, match="missing"):
        validate_hires_recipe(recipe(["full_mean"], {"full": spec}))
    with pytest.raises(ValueError, match="box"):
        validate_hires_recipe(recipe(["full_mean"],
                                     {"full": dict(FULL, box=[0, 0.6, 1, 0.5])}))


# --- numeric parts (numpy + Pillow) ------------------------------------------
@needs_numpy
def test_preprocess_shape_and_normalisation():
    img = Image.new("RGB", (600, 400), (128, 64, 255))
    x = preprocess(img, FULL)
    assert x.shape == (3, 392, 588) and x.dtype == np.float32
    expect = [(v / 255 - m) / s for v, m, s in
              zip((128, 64, 255), IMAGENET_MEAN, IMAGENET_STD)]
    # PIL's 8-bit BICUBIC may shift a flat colour by ~1 grey level (~0.02)
    np.testing.assert_allclose(x.reshape(3, -1).mean(1), expect, atol=0.02)


@needs_numpy
def test_preprocess_crops_the_box():
    # top half red, bottom half blue: a bottom-half crop must be all blue
    img = Image.new("RGB", (600, 400), (255, 0, 0))
    img.paste((0, 0, 255), (0, 200, 600, 400))
    x = preprocess(img, dict(FULL, box=[0, 0.5, 1, 1], size=[588, 196]))
    blue = (1.0 - IMAGENET_MEAN[2]) / IMAGENET_STD[2]
    np.testing.assert_allclose(x[2], blue, atol=0.02)
    assert (x[0] < 0).all()  # no red leaked in from the top half


@needs_numpy
def test_road_mask_full_frame_is_lower_half_rows():
    m = road_mask(FULL)
    assert m.shape == (42 * 28,)
    grid = m.reshape(28, 42)
    assert grid[:14].sum() == 0 and grid[14:].all()   # 14 lower rows of 28
    # a crop that starts at the road line is road everywhere
    assert road_mask(dict(FULL, box=[0, 0.5, 1, 1], size=[588, 196])).all()


@needs_numpy
def test_pool_tokens_matches_reference_formulas():
    rng = np.random.default_rng(0)
    n, d = 42 * 28, 5
    tok = rng.normal(size=(n, d)).astype(np.float32)
    mid = rng.normal(size=(n, d)).astype(np.float32)
    cls = rng.normal(size=d).astype(np.float32)
    road = road_mask(FULL)
    out = pool_tokens(POOLS_ALL, cls, tok, mid, FULL)
    np.testing.assert_allclose(out["cls"], cls)
    np.testing.assert_allclose(out["allmean"], tok.mean(0), rtol=1e-5)
    np.testing.assert_allclose(out["mean"], tok[road].mean(0), rtol=1e-5)
    np.testing.assert_allclose(out["std"], tok[road].std(0, ddof=1), rtol=1e-5)
    np.testing.assert_allclose(out["midmean"], mid[road].mean(0), rtol=1e-5)
    np.testing.assert_allclose(out["midstd"], mid[road].std(0, ddof=1), rtol=1e-5)
    gem = (np.clip(tok[road], 1e-6, None) ** 3).mean(0) ** (1 / 3)
    np.testing.assert_allclose(out["gem"], gem, rtol=1e-5)


@needs_numpy
def test_pool_tokens_rejects_wrong_token_count():
    tok = np.zeros((100, 4), dtype=np.float32)
    with pytest.raises(ValueError, match="token count"):
        pool_tokens({"mean"}, np.zeros(4), tok, None, FULL)


POOLS_ALL = {"cls", "allmean", "mean", "std", "gem", "midmean", "midstd"}
