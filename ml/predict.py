#!/usr/bin/env python3
"""
Predict RQI (1-4, lower = better road) for one or more Street View images.

Loads the saved artifact (ml/cache/rqi_model.joblib), extracts a DINOv2-small
feature for each image, and prints the continuous score + rounded RQI. Also
warns when the image does not look like a road (CLIP road filter).

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


@torch.no_grad()
def predict(paths):
    m = _load_models()
    art, proc, dino, cproc, clip = (m["art"], m["proc"], m["dino"],
                                    m["cproc"], m["clip"])
    lo, hi = art["rqi_clip"]

    prompts = ROAD_PROMPTS + NOTROAD_PROMPTS
    tinp = cproc(text=prompts, return_tensors="pt", padding=True).to(DEVICE)
    tfeat = clip.get_text_features(**tinp)
    tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)

    results = []
    for p in paths:
        img = Image.open(p).convert("RGB")

        feat = dino(**proc(images=img, return_tensors="pt").to(DEVICE)).pooler_output
        score = float(art["pipeline"].predict(feat.float().cpu().numpy())[0])
        rqi = int(np.clip(round(score), lo, hi))

        ifeat = clip.get_image_features(**cproc(images=img, return_tensors="pt").to(DEVICE))
        ifeat = ifeat / ifeat.norm(dim=-1, keepdim=True)
        pr = ((ifeat @ tfeat.T) * clip.logit_scale.exp()).softmax(-1)
        road_prob = float(pr[:, :len(ROAD_PROMPTS)].sum())

        results.append((p, score, rqi, road_prob))
    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p, score, rqi, road_prob in predict(sys.argv[1:]):
        warn = "  ⚠ not clearly a road" if road_prob < 0.55 else ""
        print(f"{os.path.basename(p):40s} RQI={rqi} ({LABELS[rqi]})  "
              f"score={score:.2f}  P(road)={road_prob:.2f}{warn}")


if __name__ == "__main__":
    main()
