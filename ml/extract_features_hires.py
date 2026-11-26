#!/usr/bin/env python3
"""
Era 8: higher-resolution ROAD-REGION DINOv2 features.

Hypothesis: the v2 recipe lets the HF image processor resize a 600x400 frame
to 384x256 and centre-crop 224x224, i.e. the backbone sees the frame at 0.64x
scale, without its outer 21% on each side and its bottom 6%. Crack-scale
pavement texture in the lower half (the road) is mostly lost. Here we feed the
backbone the road region at (near-)native or upsampled resolution instead,
and pool its patch tokens in several ways.

Result (2026-11-26): refuted, see docs/MODEL_EXPERIMENTS.md "Era 8". Road-only
features get worse with resolution, and low-res controls (road50lo, fulllo)
help the champion as much as their high-res twins.

Views (crop box in frame fractions x0,y0,x1,y1 -> backbone input size W x H,
multiples of the 14-px patch; DINOv2 interpolates its position embeddings):
  road50lo   bottom 50%, full width   -> 308x98    (scale 0.51, 22x7 tokens;
             resolution control: same crop, ~v2's pixel scale)
  road50     bottom 50%, full width   -> 588x196   (scale 0.98, 42x14 tokens)
  road50x15  bottom 50%, full width   -> 882x294   (scale 1.47, 63x21 tokens)
  roadc2x    lower-centre 60%x45%     -> 714x350   (scale 1.98, 51x25 tokens)
  full       whole frame              -> 588x392   (scale 0.98, 42x28 tokens)
  fulllo     whole frame              -> 336x224   (scale 0.56, 24x16 tokens;
             control: v2's pixel scale but no centre-crop)

Pooled outputs per view (each key = one [n_images, D] or [n, k*D] array):
  <view>_cls       CLS token (pooler_output)
  <view>_mean      mean of road-region patch tokens
  <view>_std       std  of road-region patch tokens (2nd-order texture stats)
  <view>_gem       GeM (p=3) over ReLU'd road-region patch tokens
  <view>_lc        mean of the lower-centre patches (frame y>=0.6, 0.25<=x<=0.75:
                   the lane right in front of the car, no Google logo corners)
  <view>_sp        2x3 spatial pyramid of means over the road region (6*D)
  <view>_midmean   mean of road-region tokens from an intermediate block
  <view>_midstd    std  of the same (lower-level texture features)
  <full*>_allmean  (full/fulllo only) mean over ALL patches, like v2 "patch"
"Road region" = patches whose centre is at frame y >= 0.5 (all patches of the
road crops).

Preprocessing is deliberately framework-free (PIL crop + BICUBIC resize +
ImageNet mean/std), so the backend can replicate it exactly.

Output: ml/cache/feats_hires_<backbone>_<view>.npz, rows aligned with
ml/cache/dataset_v2.csv (all rows, same order as feats_v2_<backbone>.npz).

Usage:
  /Users/i/Dev/smooth-route/.venv/bin/python ml/extract_features_hires.py \
      --backbone small --view road50
  ... --backbone small --view all          # every view for one backbone
  ... --time-only                          # throughput check on 64 frames
"""
import argparse
import json
import os
import time

import numpy as np
import pandas as pd
import torch
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")
IMAGES = os.path.join(ROOT, "data", "images")
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

BACKBONES = {"small": "facebook/dinov2-small", "base": "facebook/dinov2-base"}
# intermediate block used for the *_mid* poolings (0-based index into
# hidden_states, where hidden_states[0] is the embedding output)
MID_LAYER = {"small": 8, "base": 8}

VIEWS = {
    "road50lo": ((0.0, 0.5, 1.0, 1.0), (308, 98)),   # resolution control
    "road50": ((0.0, 0.5, 1.0, 1.0), (588, 196)),
    "road50x15": ((0.0, 0.5, 1.0, 1.0), (882, 294)),
    "roadc2x": ((0.2, 0.55, 0.8, 1.0), (714, 350)),
    "full": ((0.0, 0.0, 1.0, 1.0), (588, 392)),
    "fulllo": ((0.0, 0.0, 1.0, 1.0), (336, 224)),     # resolution control
}
PATCH = 14
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
ROAD_Y = 0.5                     # road region: frame y >= 0.5
LC_Y, LC_X = 0.6, (0.25, 0.75)   # lower-centre box
SP_GRID = (2, 3)                 # spatial-pyramid rows x cols over road region


def preprocess(img, box, size):
    """PIL image -> normalised float32 CHW array for one view."""
    w, h = img.size
    x0, y0, x1, y1 = box
    crop = img.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
    crop = crop.resize(size, Image.BICUBIC)
    a = np.asarray(crop, dtype=np.float32) / 255.0
    return ((a - MEAN) / STD).transpose(2, 0, 1)


def region_masks(box, size):
    """Boolean masks over the (rows x cols) patch grid, in frame coordinates."""
    x0, y0, x1, y1 = box
    gw, gh = size[0] // PATCH, size[1] // PATCH
    cy = y0 + (np.arange(gh) + 0.5) / gh * (y1 - y0)   # patch-centre frame y
    cx = x0 + (np.arange(gw) + 0.5) / gw * (x1 - x0)   # patch-centre frame x
    Y, X = np.meshgrid(cy, cx, indexing="ij")
    road = Y >= ROAD_Y
    lc = (Y >= LC_Y) & (X >= LC_X[0]) & (X <= LC_X[1])
    # spatial pyramid: split the road rows / all cols into SP_GRID blocks
    rows = np.flatnonzero(road.any(1))
    r_split = np.array_split(rows, SP_GRID[0])
    c_split = np.array_split(np.arange(gw), SP_GRID[1])
    sp = []
    for rs in r_split:
        for cs in c_split:
            m = np.zeros((gh, gw), dtype=bool)
            m[np.ix_(rs, cs)] = True
            sp.append(m)
    flat = lambda m: torch.from_numpy(m.reshape(-1))  # noqa: E731
    return {"road": flat(road), "lc": flat(lc),
            "sp": [flat(m) for m in sp], "all": flat(np.ones_like(road))}


def pool(tokens, mid, masks, view):
    """tokens/mid: [B, N, D] patch tokens (final / intermediate block)."""
    r = masks["road"].to(tokens.device)
    road = tokens[:, r]
    out = {
        "mean": road.mean(1),
        "std": road.std(1),
        "gem": road.clamp(min=1e-6).pow(3).mean(1).pow(1 / 3),
        "lc": tokens[:, masks["lc"].to(tokens.device)].mean(1),
        "sp": torch.cat([tokens[:, m.to(tokens.device)].mean(1)
                         for m in masks["sp"]], 1),
        "midmean": mid[:, r].mean(1),
        "midstd": mid[:, r].std(1),
    }
    if view.startswith("full"):
        out["allmean"] = tokens.mean(1)
    return out


@torch.no_grad()
def extract(paths, backbone, view, batch, limit=None):
    from transformers import AutoModel

    model = AutoModel.from_pretrained(BACKBONES[backbone]).to(DEVICE).eval()
    n_reg = getattr(model.config, "num_register_tokens", 0) or 0
    start = 1 + n_reg
    box, size = VIEWS[view]
    masks = region_masks(box, size)
    paths = paths[:limit] if limit else paths
    acc, t0 = {}, time.time()
    for i in range(0, len(paths), batch):
        arr = np.stack([preprocess(Image.open(p).convert("RGB"), box, size)
                        for p in paths[i:i + batch]])
        x = torch.from_numpy(arr).to(DEVICE)
        o = model(pixel_values=x, output_hidden_states=True)
        tok = o.last_hidden_state[:, start:]
        mid = o.hidden_states[MID_LAYER[backbone]][:, start:]
        feats = pool(tok, mid, masks, view)
        feats["cls"] = o.pooler_output
        for k, v in feats.items():
            acc.setdefault(f"{view}_{k}", []).append(v.float().cpu().numpy())
        done = i + len(arr)
        rate = done / (time.time() - t0)
        print(f"   {backbone}/{view} {done}/{len(paths)}  {rate:.1f} img/s",
              end="\r", flush=True)
    print()
    dt = time.time() - t0
    return {k: np.concatenate(v) for k, v in acc.items()}, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", choices=list(BACKBONES), default="small")
    ap.add_argument("--view", default="road50",
                    help=f"one of {list(VIEWS)} or 'all'")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--time-only", action="store_true",
                    help="throughput check on 64 frames, no cache written")
    args = ap.parse_args()

    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    paths = [os.path.join(IMAGES, f) for f in df["image_filename"]]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"{len(missing)} images missing, e.g. {missing[0]}")
    views = list(VIEWS) if args.view == "all" else [args.view]
    print(f"{len(paths)} frames, device={DEVICE}, backbone={args.backbone}")
    for view in views:
        feats, dt = extract(paths, args.backbone, view, args.batch,
                            limit=64 if args.time_only else None)
        n = len(next(iter(feats.values())))
        per = dt / n
        print(f"   {view}: {n / dt:.1f} img/s -> 17.6k frames ≈ "
              f"{17_600 * per / 60:.0f} min")
        if args.time_only:
            continue
        out = os.path.join(CACHE, f"feats_hires_{args.backbone}_{view}.npz")
        meta = {"backbone": BACKBONES[args.backbone], "view": view,
                "box": VIEWS[view][0], "size": VIEWS[view][1],
                "mid_layer": MID_LAYER[args.backbone], "sec_per_img": per}
        np.savez_compressed(out, files=df["image_filename"].values,
                            meta=json.dumps(meta), **feats)
        print(f"   saved {os.path.relpath(out, ROOT)}: "
              + ", ".join(f"{k}{v.shape[1:]}" for k, v in feats.items()))


if __name__ == "__main__":
    main()
