#!/usr/bin/env python3
"""
Predict RQI (1-4, lower = better road) for one or more Street View images.

Loads the saved artifact (ml/cache/rqi_model.joblib), builds the feature
vector its `feature_recipe` asks for (DINOv2 views/tokens, optionally CLIP),
and prints the continuous score, the RQI class (tuned ordinal cut-points),
and the calibrated P(bad road). Warns when the image does not look like a
road (CLIP road filter).

Usage:
  .venv/bin/python ml/predict.py path/to/image.jpg [more.jpg ...]
"""
import os
import sys

import joblib
import numpy as np
import torch
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

ROAD_PROMPTS = [
    "a photo of a road or street with an asphalt driving surface",
    "a street view photo of a paved road seen from a car",
]
NOTROAD_PROMPTS = [
    "an indoor scene inside a building, a lobby or a shop",
    "a photo of people, a sidewalk, a plaza or pedestrian area with no road",
]
LABELS = {1: "excellent", 2: "good", 3: "fair", 4: "poor"}

_cache = {}


def _load_models():
    if _cache:
        return _cache
    from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor

    art = joblib.load(os.path.join(CACHE, "rqi_model.joblib"))
    proc = AutoImageProcessor.from_pretrained(art["backbone"])
    dino = AutoModel.from_pretrained(art["backbone"]).to(DEVICE).eval()
    cproc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(DEVICE).eval()
    _cache.update(art=art, proc=proc, dino=dino, cproc=cproc, clip=clip)
    return _cache


def _dino_features(img, art, proc, dino):
    recipe = art.get("feature_recipe")
    if not recipe:  # v1 artifact
        feat = dino(**proc(images=img, return_tensors="pt").to(DEVICE)).pooler_output
        return feat.float().cpu().numpy()

    keys = recipe["keys"]
    views = [img]
    flip_idx = crop_idx = None
    if any(k.endswith("_flip") or k.endswith("_avg") for k in keys):
        flip_idx = len(views)
        views.append(img.transpose(Image.FLIP_LEFT_RIGHT))
    if any(k.endswith("_crop") for k in keys):
        crop_idx = len(views)
        w, h = img.size
        views.append(img.crop((0, int(h * recipe.get("crop_top", 0.35)), w, h)))

    out = dino(**proc(images=views, return_tensors="pt").to(DEVICE))
    cls = out.pooler_output.float().cpu().numpy()
    patch = out.last_hidden_state[:, 1:].mean(1).float().cpu().numpy()

    pool = {"cls": cls[0], "patch": patch[0]}
    if flip_idx is not None:
        pool["cls_flip"], pool["patch_flip"] = cls[flip_idx], patch[flip_idx]
        pool["cls_avg"] = (pool["cls"] + pool["cls_flip"]) / 2
        pool["patch_avg"] = (pool["patch"] + pool["patch_flip"]) / 2
    if crop_idx is not None:
        pool["cls_crop"], pool["patch_crop"] = cls[crop_idx], patch[crop_idx]
    return pool, keys


@torch.no_grad()
def predict(paths):
    m = _load_models()
    art, proc, dino, cproc, clip = (m["art"], m["proc"], m["dino"],
                                    m["cproc"], m["clip"])
    thresholds = art.get("thresholds")
    lo, hi = art["rqi_clip"]
    calibrator = art.get("p_bad_calibrator")

    prompts = ROAD_PROMPTS + NOTROAD_PROMPTS
    tinp = cproc(text=prompts, return_tensors="pt", padding=True).to(DEVICE)
    tfeat = clip.get_text_features(**tinp)
    tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)

    results = []
    for p in paths:
        img = Image.open(p).convert("RGB")

        ifeat = clip.get_image_features(**cproc(images=img, return_tensors="pt").to(DEVICE))
        nfeat = ifeat / ifeat.norm(dim=-1, keepdim=True)
        pr = ((nfeat @ tfeat.T) * clip.logit_scale.exp()).softmax(-1)
        road_prob = float(pr[:, :len(ROAD_PROMPTS)].sum())

        res = _dino_features(img, art, proc, dino)
        if isinstance(res, tuple):
            pool, keys = res
            if art["feature_recipe"].get("needs_clip"):
                pool["clip"] = ifeat.float().cpu().numpy()[0]
            feat = np.concatenate([pool[k] for k in keys])[None, :]
        else:
            feat = res
        score = float(art["pipeline"].predict(feat)[0])

        if thresholds:
            rqi = int(np.digitize(score, thresholds) + 1)
        else:
            rqi = int(np.clip(round(score), lo, hi))
        p_bad = (float(calibrator.predict([score])[0])
                 if calibrator is not None else None)

        results.append((p, score, rqi, p_bad, road_prob))
    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p, score, rqi, p_bad, road_prob in predict(sys.argv[1:]):
        warn = "  ⚠ not clearly a road" if road_prob < 0.55 else ""
        pb = f"  P(bad)={p_bad:.2f}" if p_bad is not None else ""
        print(f"{os.path.basename(p):40s} RQI={rqi} ({LABELS[rqi]})  "
              f"score={score:.2f}{pb}  P(road)={road_prob:.2f}{warn}")


if __name__ == "__main__":
    main()
