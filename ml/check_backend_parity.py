#!/usr/bin/env python3
"""
Backend parity check: does backend/app/services/dino_service.py rebuild the
SAME feature vector (and score) for an artifact as the training caches did?

Loads the artifact through the real DinoInferenceService (its recipe parser,
preprocessing and backbone), scores N labelled frames, and compares with
ml/save_model_v2.build_features (the cached training features) for the same
frames. Also reports backend throughput (s/frame -> minutes for 17.6k frames).

Usage:
  /Users/i/Dev/smooth-route/.venv/bin/python ml/check_backend_parity.py \
      ml/cache/rqi_model_candidate.joblib [--n 40]
Exit 0 if every score matches within --tol (default 0.02 RQI), else 1.
"""
import argparse
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from evaluate_artifact import _backbone_key  # noqa: E402
from save_model_v2 import build_features  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--tol", type=float, default=0.02)
    args = ap.parse_args()

    import torch

    import app.services.dino_service as D

    torch.set_grad_enabled(False)  # _features normally runs under predict_score's no_grad

    D.MODEL_PATH = os.path.abspath(args.artifact)
    svc = D.DinoInferenceService()
    svc.load_model()
    art = joblib.load(D.MODEL_PATH)
    X_cache = build_features(art["feature_recipe"]["name"],
                             _backbone_key(art["backbone"]))
    df = pd.read_csv(os.path.join(ROOT, "ml", "cache", "dataset_v2.csv"))
    idx = np.random.default_rng(0).choice(len(df), args.n, replace=False)

    from PIL import Image
    feat_err, score_err, t = [], [], []
    svc._features(Image.open(os.path.join(ROOT, "data", "images",
                                          df["image_filename"][idx[0]])).convert("RGB"))
    for i in idx:
        img = Image.open(os.path.join(ROOT, "data", "images",
                                      df["image_filename"][i])).convert("RGB")
        t0 = time.time()
        f = svc._features(img)[0]
        t.append(time.time() - t0)
        ref = X_cache[i]
        feat_err.append(np.abs(f - ref).max() / (np.abs(ref).max() + 1e-9))
        s_b = float(svc.pipeline.predict(f[None])[0])
        s_c = float(svc.pipeline.predict(ref[None])[0])
        score_err.append(abs(s_b - s_c))
    sec = float(np.median(t))
    print(f"artifact : {os.path.relpath(D.MODEL_PATH, ROOT)}  "
          f"(recipe {art['feature_recipe']['name']}, {art['backbone']})")
    print(f"frames   : {args.n}  device={svc.device}")
    print(f"feature  : max rel. abs diff {max(feat_err):.2e} "
          f"(median {np.median(feat_err):.2e})")
    print(f"score    : max |Δ| {max(score_err):.4f}  (median {np.median(score_err):.4f})")
    print(f"speed    : {sec * 1000:.0f} ms/frame (median, batch 1) -> "
          f"17.6k frames ≈ {17_600 * sec / 60:.0f} min")
    ok = max(score_err) <= args.tol
    print("PARITY OK" if ok else f"PARITY FAIL (> {args.tol})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
