#!/usr/bin/env python3
"""
V2 feature extraction: multiple frozen-backbone feature variants per image so
the training script can mix-and-match without re-running the backbone.

Per labelled image present on disk, saves:
  - DINOv2 CLS token                      (cls)
  - DINOv2 mean of patch tokens           (patch)   - texture signal
  - both again for the horizontal flip    (cls_flip, patch_flip)
  - both for a bottom-crop (road region)  (cls_crop, patch_crop)
  - CLIP-B/32 image embedding + road prob (clip.npz, shared)

Outputs:
  ml/cache/dataset_v2.csv           manifest (filename, rqi, is_road_prob)
  ml/cache/feats_v2_<backbone>.npz  aligned feature arrays
  ml/cache/clip_v2.npz              CLIP embeddings + road prob

Usage:
  .venv/bin/python ml/extract_features_v2.py                 # dinov2-small
  .venv/bin/python ml/extract_features_v2.py --backbone base # dinov2-base
"""
import argparse
import os

import numpy as np
import pandas as pd
import torch
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "ml", "labels.csv")
# The backend saves route imagery under backend/data/images (see
# config.resolve_data_dir); the original training dump lives in data/images.
# Labelled images may sit in either, so look both places.
IMAGE_DIRS = [
    os.path.join(ROOT, "data", "images"),
    os.path.join(ROOT, "backend", "data", "images"),
]
CACHE = os.path.join(ROOT, "ml", "cache")
os.makedirs(CACHE, exist_ok=True)


def find_image(filename):
    for d in IMAGE_DIRS:
        p = os.path.join(d, str(filename))
        if os.path.exists(p):
            return p
    return None

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
BATCH = 32
CROP_TOP = 0.35  # bottom crop keeps lower 65% of the image (road surface)

BACKBONES = {
    "small": "facebook/dinov2-small",
    "base": "facebook/dinov2-base",
}

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
    df["path"] = df["image_filename"].apply(find_image)
    df = df[df["path"].notna()].drop_duplicates("image_filename").reset_index(drop=True)
    return df[["image_filename", "manual_rqi", "rqi", "tags", "path"]]


def batches(lst):
    for i in range(0, len(lst), BATCH):
        yield i, lst[i : i + BATCH]


def views(img):
    """original, hflip, bottom-crop views of a PIL image."""
    w, h = img.size
    crop = img.crop((0, int(h * CROP_TOP), w, h))
    return img, img.transpose(Image.FLIP_LEFT_RIGHT), crop


@torch.no_grad()
def extract_dinov2(paths, model_name):
    from transformers import AutoImageProcessor, AutoModel

    print(f">> loading {model_name} ...")
    proc = AutoImageProcessor.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(DEVICE).eval()

    out = {k: [] for k in ("cls", "patch", "cls_flip", "patch_flip",
                           "cls_crop", "patch_crop")}
    for i, batch in batches(paths):
        imgs = [Image.open(p).convert("RGB") for p in batch]
        packs = [[], [], []]
        for im in imgs:
            for slot, v in zip(packs, views(im)):
                slot.append(v)
        for name_cls, name_patch, pack in (
            ("cls", "patch", packs[0]),
            ("cls_flip", "patch_flip", packs[1]),
            ("cls_crop", "patch_crop", packs[2]),
        ):
            inp = proc(images=pack, return_tensors="pt").to(DEVICE)
            o = model(**inp)
            cls = o.pooler_output                     # [B, D]
            patch = o.last_hidden_state[:, 1:].mean(1)  # mean of patch tokens
            out[name_cls].append(cls.float().cpu().numpy())
            out[name_patch].append(patch.float().cpu().numpy())
        print(f"   dinov2 {i + len(batch)}/{len(paths)}", end="\r")
    print()
    return {k: np.concatenate(v, axis=0) for k, v in out.items()}


@torch.no_grad()
def extract_clip(paths):
    from transformers import CLIPModel, CLIPProcessor

    print(">> loading CLIP-B/32 ...")
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(DEVICE).eval()

    prompts = ROAD_PROMPTS + NOTROAD_PROMPTS
    tinp = proc(text=prompts, return_tensors="pt", padding=True).to(DEVICE)
    tfeat = model.get_text_features(**tinp)
    tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)

    embs, probs = [], []
    for i, batch in batches(paths):
        imgs = [Image.open(p).convert("RGB") for p in batch]
        iinp = proc(images=imgs, return_tensors="pt").to(DEVICE)
        ifeat = model.get_image_features(**iinp)
        nfeat = ifeat / ifeat.norm(dim=-1, keepdim=True)
        logits = (nfeat @ tfeat.T) * model.logit_scale.exp()
        p_road = logits.softmax(-1)[:, : len(ROAD_PROMPTS)].sum(-1)
        embs.append(ifeat.float().cpu().numpy())
        probs.append(p_road.float().cpu().numpy())
        print(f"   clip {i + len(batch)}/{len(paths)}", end="\r")
    print()
    return np.concatenate(embs, 0), np.concatenate(probs, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", choices=list(BACKBONES), default="small")
    args = ap.parse_args()

    df = load_manifest()
    print(f"Labelled images present on disk: {len(df)}  (device={DEVICE})")
    paths = list(df.pop("path"))

    feats = extract_dinov2(paths, BACKBONES[args.backbone])
    np.savez_compressed(
        os.path.join(CACHE, f"feats_v2_{args.backbone}.npz"), **feats
    )
    print(f"Saved {args.backbone} features:",
          {k: v.shape for k, v in feats.items()})

    clip_path = os.path.join(CACHE, "clip_v2.npz")
    manifest_path = os.path.join(CACHE, "dataset_v2.csv")
    need_clip = True
    if os.path.exists(clip_path) and os.path.exists(manifest_path):
        old = pd.read_csv(manifest_path)
        need_clip = list(old["image_filename"]) != list(df["image_filename"])
    if need_clip:
        emb, p_road = extract_clip(paths)
        np.savez_compressed(clip_path, clip=emb, road_prob=p_road)
        df["is_road_prob"] = p_road
        df.to_csv(manifest_path, index=False)
        print(f"Saved CLIP embeddings {emb.shape} + manifest ({len(df)} rows)")
    else:
        print("CLIP cache is current, skipping.")


if __name__ == "__main__":
    main()
