#!/usr/bin/env python3
"""
Compare frozen backbones for the RQI head with identical 5-fold stratified CV.
Extracts features per backbone (cached) and reports MAE / ±1 / QWK.

Usage:  .venv/bin/python ml/compare_backbones.py
"""
import os

import numpy as np
import pandas as pd
import torch
from PIL import Image
from sklearn.linear_model import Ridge
from sklearn.metrics import cohen_kappa_score, mean_absolute_error
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "data", "images")
CACHE = os.path.join(ROOT, "ml", "cache")
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
BATCH = 32
BACKBONES = ["facebook/dinov2-small", "facebook/dinov2-base"]


@torch.no_grad()
def extract(backbone, paths):
    tag = backbone.split("/")[-1]
    fp = os.path.join(CACHE, f"feat_{tag}.npz")
    if os.path.exists(fp):
        return np.load(fp)["x"]
    from transformers import AutoImageProcessor, AutoModel

    print(f">> extracting {backbone} ...")
    proc = AutoImageProcessor.from_pretrained(backbone)
    model = AutoModel.from_pretrained(backbone).to(DEVICE).eval()
    out = []
    for i in range(0, len(paths), BATCH):
        imgs = [Image.open(p).convert("RGB") for p in paths[i:i + BATCH]]
        inp = proc(images=imgs, return_tensors="pt").to(DEVICE)
        out.append(model(**inp).pooler_output.float().cpu().numpy())
        print(f"   {i + len(imgs)}/{len(paths)}", end="\r")
    print()
    x = np.concatenate(out)
    np.savez_compressed(fp, x=x)
    return x


def cv(X, y, yc):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    maes, off1s, qwks = [], [], []
    for tr, te in skf.split(X, yc):
        sc = StandardScaler().fit(X[tr])
        m = Ridge(alpha=10.0).fit(sc.transform(X[tr]), y[tr])
        pred = np.clip(np.round(m.predict(sc.transform(X[te]))), 1, 4).astype(int)
        maes.append(mean_absolute_error(yc[te], pred))
        off1s.append(np.mean(np.abs(yc[te] - pred) <= 1))
        qwks.append(cohen_kappa_score(yc[te], pred, weights="quadratic", labels=[1, 2, 3, 4]))
    return np.mean(maes), np.mean(off1s), np.mean(qwks)


def main():
    df = pd.read_csv(os.path.join(CACHE, "dataset.csv"))
    df = df[(df["rqi"] != 5) & (df["is_road_prob"] >= 0.55)].reset_index(drop=True)
    paths = [os.path.join(IMAGES, f) for f in df["image_filename"]]
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)

    print(f"{len(df)} images | 5-fold stratified CV\n")
    print(f"{'backbone':22s} {'dim':>5} {'MAE':>7} {'±1':>7} {'QWK':>7}")
    for b in BACKBONES:
        X = extract(b, paths)
        mae, off1, qwk = cv(X, y, yc)
        print(f"{b.split('/')[-1]:22s} {X.shape[1]:>5} {mae:>7.3f} {off1:>7.3f} {qwk:>7.3f}")


if __name__ == "__main__":
    main()
