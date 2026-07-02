#!/usr/bin/env python3
"""
Extract frozen-backbone features + a road/not-road junk score for every
labelled image that is present on disk.

Outputs (cached, so training can iterate without re-running this):
  ml/cache/dataset.csv   - one row per usable image (filename, rqi, is_road_prob)
  ml/cache/features.npz  - DINOv2 CLS features aligned with dataset.csv row order

Runs on the Mac (MPS). First run downloads DINOv2-small + CLIP-B/32 weights.

Usage:  .venv/bin/python ml/extract_features.py
"""
import os
import sys

import numpy as np
import pandas as pd
import torch
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "ml", "labels.csv")
IMAGES = os.path.join(ROOT, "data", "images")
CACHE = os.path.join(ROOT, "ml", "cache")
os.makedirs(CACHE, exist_ok=True)

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
BATCH = 32

# CLIP text probes for the "is this actually a drivable road?" filter.
ROAD_PROMPTS = [
    "a photo of a road or street with an asphalt driving surface",
    "a street view photo of a paved road seen from a car",
]
NOTROAD_PROMPTS = [
    "an indoor scene inside a building, a lobby or a shop",
    "a photo of people, a sidewalk, a plaza or pedestrian area with no road",
]


def load_manifest():
    df = pd.read_csv(LABELS)
    df = df[df["manual_rqi"].notna()].copy()
    df["rqi"] = df["manual_rqi"].round().clip(1, 5).astype(int)
    df["present"] = df["image_filename"].apply(
        lambda f: os.path.exists(os.path.join(IMAGES, str(f)))
    )
    df = df[df["present"]].drop_duplicates("image_filename").reset_index(drop=True)
    return df[["image_filename", "manual_rqi", "rqi", "tags"]]


def iter_batches(paths):
    for i in range(0, len(paths), BATCH):
        yield i, paths[i : i + BATCH]


@torch.no_grad()
def extract_dinov2(paths):
    from transformers import AutoImageProcessor, AutoModel

    print(">> loading DINOv2-small ...")
    proc = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
    model = AutoModel.from_pretrained("facebook/dinov2-small").to(DEVICE).eval()

    feats = []
    for i, batch in iter_batches(paths):
        imgs = [Image.open(p).convert("RGB") for p in batch]
        inp = proc(images=imgs, return_tensors="pt").to(DEVICE)
        out = model(**inp)
        cls = out.pooler_output  # [B, 384]
        feats.append(cls.float().cpu().numpy())
        print(f"   dinov2 {i + len(batch)}/{len(paths)}", end="\r")
    print()
    return np.concatenate(feats, axis=0)


@torch.no_grad()
def road_probability(paths):
    from transformers import CLIPModel, CLIPProcessor

    print(">> loading CLIP-B/32 for junk filter ...")
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(DEVICE).eval()

    prompts = ROAD_PROMPTS + NOTROAD_PROMPTS
    n_road = len(ROAD_PROMPTS)
    tinp = proc(text=prompts, return_tensors="pt", padding=True).to(DEVICE)
    tfeat = model.get_text_features(**tinp)
    tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)

    probs = []
    for i, batch in iter_batches(paths):
        imgs = [Image.open(p).convert("RGB") for p in batch]
        iinp = proc(images=imgs, return_tensors="pt").to(DEVICE)
        ifeat = model.get_image_features(**iinp)
        ifeat = ifeat / ifeat.norm(dim=-1, keepdim=True)
        logits = (ifeat @ tfeat.T) * model.logit_scale.exp()
        p = logits.softmax(dim=-1)
        p_road = p[:, :n_road].sum(dim=-1)  # P(any road prompt)
        probs.append(p_road.float().cpu().numpy())
        print(f"   clip {i + len(batch)}/{len(paths)}", end="\r")
    print()
    return np.concatenate(probs, axis=0)


def main():
    df = load_manifest()
    print(f"Usable labelled images (present on disk): {len(df)}")
    print(f"Device: {DEVICE}\n")

    paths = [os.path.join(IMAGES, f) for f in df["image_filename"]]

    feats = extract_dinov2(paths)
    df["is_road_prob"] = road_probability(paths)

    np.savez_compressed(os.path.join(CACHE, "features.npz"), dinov2=feats)
    df.to_csv(os.path.join(CACHE, "dataset.csv"), index=False)

    print(f"\nSaved features {feats.shape} -> ml/cache/features.npz")
    print(f"Saved manifest ({len(df)} rows) -> ml/cache/dataset.csv")

    # quick junk report
    for thr in (0.5, 0.6, 0.7):
        n = int((df["is_road_prob"] < thr).sum())
        print(f"  images with P(road) < {thr}: {n}")


if __name__ == "__main__":
    main()
