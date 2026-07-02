#!/usr/bin/env python3
"""
Train the final RQI head on ALL usable data and save a deployable artifact.

Uses the cached DINOv2 features. Fits StandardScaler + Ridge on every RQI 1-4
image that passes the road filter, then saves scaler + model + metadata to
ml/cache/rqi_model.joblib. CV numbers (from ml/train.py) are the honest quality
estimate; this artifact is that same recipe trained on 100% of the data.

Usage:  .venv/bin/python ml/save_model.py
"""
import os
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True
ROAD_PROB_MIN = 0.55
RQI_MIN, RQI_MAX = 1, 4


def main():
    df = pd.read_csv(os.path.join(CACHE, "dataset.csv"))
    X = np.load(os.path.join(CACHE, "features.npz"))["dinov2"]
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X[keep], df[keep].reset_index(drop=True)
    y = df["manual_rqi"].values.astype(float)

    pipe = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(X, y)

    artifact = {
        "pipeline": pipe,
        "backbone": "facebook/dinov2-small",
        "feature": "pooler_output (CLS, dim=384)",
        "rqi_clip": [RQI_MIN, RQI_MAX],
        "road_prob_min": ROAD_PROB_MIN,
        "n_train": int(len(df)),
        "scale_meaning": "1=excellent .. 4=poor (lower=better road)",
        "cv_metrics": {"mae": 0.30, "off_by_one_acc": 0.996, "qwk": 0.83},
    }
    out = os.path.join(CACHE, "rqi_model.joblib")
    joblib.dump(artifact, out)
    print(f"Trained on {len(df)} images. Saved -> {out}")
    print(json.dumps({k: v for k, v in artifact.items() if k != "pipeline"}, indent=2))


if __name__ == "__main__":
    main()
