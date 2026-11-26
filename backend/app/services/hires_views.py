"""
Hi-resolution view features for RQI recipes (torch-free helpers).

An artifact's ``feature_recipe`` may name keys ``"<view>_<pool>"`` whose view
is described in ``feature_recipe["hires_views"]`` (written by
ml/save_model_v2.py, extracted for training by ml/extract_features_hires.py):

    {"full": {"box": [0, 0, 1, 1], "size": [588, 392],
              "mid_layer": 8, "road_y": 0.5}}

For such a view the frame is cropped to ``box`` (frame fractions
x0, y0, x1, y1), resized with BICUBIC to ``size`` (W, H; multiples of the
14-px patch) and normalised with the ImageNet mean/std. The backbone runs on
that tensor directly (no HF processor, no centre-crop). Pools:

    cls        CLS token of the last layer
    allmean    mean over all patch tokens (last layer)
    mean/std   mean / std (ddof=1) over the ROAD patches (last layer)
    gem        GeM p=3 over ReLU'd road patches (last layer)
    midmean/midstd  mean / std over the road patches of hidden_states[mid_layer]

Road patches are those whose centre lies at frame y >= ``road_y``.

This module holds the pure parts (spec validation, preprocessing, patch-grid
masks, pooling on numpy token arrays) so they can be unit-tested without
torch; dino_service.py runs the backbone and calls in here. The training-side
code in ml/extract_features_hires.py must stay numerically identical.
"""
from __future__ import annotations

PATCH = 14
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
LAST_LAYER_POOLS = ("cls", "allmean", "mean", "std", "gem")
MID_POOLS = ("midmean", "midstd")
POOLS = LAST_LAYER_POOLS + MID_POOLS
SPEC_KEYS = ("box", "size", "mid_layer", "road_y")


def split_key(key: str, views: dict) -> tuple[str, str] | None:
    """``"full_midmean" -> ("full", "midmean")`` if ``full`` is a hi-res view,
    else None (the key belongs to the classic 224-px views)."""
    if "_" not in key:
        return None
    view, pool = key.split("_", 1)
    return (view, pool) if view in views else None


def validate_hires_recipe(recipe: dict) -> None:
    """Raise ValueError if the recipe's hi-res keys/specs are unusable."""
    views = recipe.get("hires_views") or {}
    for name, spec in views.items():
        missing = [k for k in SPEC_KEYS if k not in spec]
        if missing:
            raise ValueError(f"hires view '{name}' is missing {missing}")
        w, h = spec["size"]
        if w % PATCH or h % PATCH:
            raise ValueError(f"hires view '{name}' size {spec['size']} is not "
                             f"a multiple of the {PATCH}-px patch")
        x0, y0, x1, y1 = spec["box"]
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError(f"hires view '{name}' box {spec['box']} is invalid")
    for key in recipe.get("keys", []):
        parsed = split_key(key, views)
        if parsed and parsed[1] not in POOLS:
            raise ValueError(f"recipe key '{key}': unknown pool '{parsed[1]}' "
                             f"(supported: {', '.join(POOLS)})")


def needed_views(recipe: dict) -> dict:
    """view name -> set of pools the recipe asks for (empty if none)."""
    views = recipe.get("hires_views") or {}
    out: dict = {}
    for key in recipe.get("keys", []):
        parsed = split_key(key, views)
        if parsed:
            out.setdefault(parsed[0], set()).add(parsed[1])
    return out


def preprocess(img, spec):
    """PIL image -> float32 array [3, H, W] (crop, BICUBIC resize, normalise)."""
    import numpy as np
    from PIL import Image

    w, h = img.size
    x0, y0, x1, y1 = spec["box"]
    crop = img.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
    crop = crop.resize(tuple(spec["size"]), Image.BICUBIC)
    a = np.asarray(crop, dtype=np.float32) / 255.0
    mean = np.array(IMAGENET_MEAN, dtype=np.float32)
    std = np.array(IMAGENET_STD, dtype=np.float32)
    return ((a - mean) / std).transpose(2, 0, 1)


def road_mask(spec):
    """Boolean [n_patches] mask (row-major patch grid): patch centre y >= road_y."""
    import numpy as np

    _, y0, _, y1 = spec["box"]
    gw, gh = spec["size"][0] // PATCH, spec["size"][1] // PATCH
    cy = y0 + (np.arange(gh) + 0.5) / gh * (y1 - y0)
    return np.repeat(cy >= spec["road_y"], gw)


def pool_tokens(pools, cls, tokens, mid_tokens, spec):
    """Pool one image's tokens.

    cls: [D]; tokens / mid_tokens: [n_patches, D] (patch tokens only, no CLS or
    register tokens) from the last layer / hidden_states[mid_layer].
    Returns {pool: [D] float32}.
    """
    import numpy as np

    road = road_mask(spec)
    if road.shape[0] != tokens.shape[0]:
        raise ValueError(f"token count {tokens.shape[0]} != patch grid "
                         f"{road.shape[0]} for size {spec['size']}")
    t = np.asarray(tokens, dtype=np.float32)
    r = t[road]
    out = {}
    for p in pools:
        if p == "cls":
            v = np.asarray(cls, dtype=np.float32)
        elif p == "allmean":
            v = t.mean(0)
        elif p == "mean":
            v = r.mean(0)
        elif p == "std":
            v = r.std(0, ddof=1)
        elif p == "gem":
            v = np.power(np.power(np.clip(r, 1e-6, None), 3).mean(0), 1 / 3)
        elif p in MID_POOLS:
            m = np.asarray(mid_tokens, dtype=np.float32)[road]
            v = m.mean(0) if p == "midmean" else m.std(0, ddof=1)
        else:
            raise ValueError(f"unknown pool '{p}'")
        out[p] = v.astype(np.float32)
    return out
