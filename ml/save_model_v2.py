#!/usr/bin/env python3
"""
Train the final v2 RQI model on ALL usable data and save a deployable artifact.

Adds over v1:
  - configurable feature recipe (which DINOv2 views/tokens + optional CLIP)
  - SVR-RBF head (the CV winner) with tuned hyperparameters
  - ordinal cut-points tuned on out-of-fold predictions (instead of fixed .5
    rounding), stored in the artifact
  - isotonic P(bad road) calibration fitted on out-of-fold predictions, so the
    artifact can answer "how sure are we this road is bad (RQI>=3)?" honestly
  - per-predicted-class empirical reliability table from CV (what the true
    class distribution looks like when the model outputs k)

All out-of-fold numbers come from the official SPATIAL CV (ml/spatial_cv.py:
1 km grid cells, StratifiedGroupKFold, seed 42, nested cut-points), so the
model card (`cv_metrics`, `reliability`) and the P(bad) calibrator describe
performance on streets the model has never seen — not the leaky random-fold
numbers of the first v2 artifact.

The recipe is stored machine-readably in the artifact; inference code
(ml/predict.py, backend dino_service) builds features from it.

Usage:  .venv/bin/python ml/save_model_v2.py --recipe cls+patch [--head svr-rbf]
        # era 8 candidate (never overwrite the champion; the lead promotes):
        .venv/bin/python ml/save_model_v2.py --recipe cls+patch+full_mid \
            --backbone base --out rqi_model_candidate.joblib
"""
import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from spatial_cv import tune_thresholds  # noqa: E402,F401  (re-exported)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")

DROP_RQI5 = True
ROAD_PROB_MIN = 0.55
RQI_MIN, RQI_MAX = 1, 4
BAD_FROM = 3
N_SPLITS = S.N_SPLITS
SEED = S.SEED

# recipe -> (feature keys concatenated in order, needs_clip)
# keys refer to arrays in feats_v2_<backbone>.npz; "clip" comes from clip_v2.npz
RECIPES = {
    "cls": (["cls"], False),
    "cls+patch": (["cls", "patch"], False),
    "cls+patch+clip": (["cls", "patch", "clip"], True),
    "cls+patch flipavg": (["cls_avg", "patch_avg"], False),
    "all": (["cls_avg", "patch_avg", "patch_crop", "clip"], True),
    # era 8: + mean/std of intermediate-block (8) tokens over the road half of
    # the full frame seen at native resolution (588x392, no centre-crop)
    "cls+patch+full_mid": (["cls", "patch", "full_midmean", "full_midstd"], False),
}

# Hi-res views (ml/extract_features_hires.py). A recipe key "<view>_<pool>"
# whose prefix is listed here comes from feats_hires_<backbone>_<view>.npz,
# and the spec is written into the artifact's feature_recipe["hires_views"]
# so the backend (app/services/hires_views.py) rebuilds the same features:
# crop `box` (frame fractions x0,y0,x1,y1) -> BICUBIC resize to `size` (W,H)
# -> ImageNet mean/std; pools run over patches whose centre is at frame
# y >= road_y; "mid*" pools read hidden_states[mid_layer].
HIRES_VIEWS = {
    "full": {"box": [0.0, 0.0, 1.0, 1.0], "size": [588, 392],
             "mid_layer": 8, "road_y": 0.5},
}


def hires_views_for(keys):
    return sorted({k.split("_", 1)[0] for k in keys
                   if "_" in k and k.split("_", 1)[0] in HIRES_VIEWS})

HEADS = {
    "ridge": lambda: RidgeCV(alphas=[1, 3, 10, 30, 100, 300]),
    # tuned on 5-fold CV (ml/tune_svr.py): C=1, gamma=scale, eps=0.05
    "svr-rbf": lambda: SVR(C=1.0, gamma="scale", epsilon=0.05),
}

# backbone key -> full HF name written into the artifact (the backend loads this
# name). Must stay in sync with extract_features_v2.BACKBONES.
BACKBONE_NAMES = {
    "small": "facebook/dinov2-small",
    "base": "facebook/dinov2-base",
    "v3small": "facebook/dinov3-vits16-pretrain-lvd1689m",
    "v3base": "facebook/dinov3-vitb16-pretrain-lvd1689m",
}


def build_features(recipe, backbone):
    F = np.load(os.path.join(CACHE, f"feats_v2_{backbone}.npz"))
    C = np.load(os.path.join(CACHE, "clip_v2.npz"))
    pool = {k: F[k] for k in F.files}
    pool["cls_avg"] = (pool["cls"] + pool["cls_flip"]) / 2
    pool["patch_avg"] = (pool["patch"] + pool["patch_flip"]) / 2
    pool["clip"] = C["clip"]
    keys, _ = RECIPES[recipe]
    for view in hires_views_for(keys):
        H = np.load(os.path.join(CACHE, f"feats_hires_{backbone}_{view}.npz"),
                    allow_pickle=True)
        meta, spec = json.loads(str(H["meta"])), HIRES_VIEWS[view]
        if (list(meta["box"]) != spec["box"] or list(meta["size"]) != spec["size"]
                or meta["mid_layer"] != spec["mid_layer"]):
            raise ValueError(f"feats_hires_{backbone}_{view}.npz was extracted "
                             f"with {meta}, recipe expects {spec}")
        if len(H["files"]) != len(F["cls"]):
            raise ValueError(f"feats_hires_{backbone}_{view}.npz misaligned")
        pool.update({k: H[k] for k in H.files if k.startswith(view + "_")})
    return np.hstack([pool[k] for k in keys])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", choices=list(RECIPES), default="cls+patch")
    ap.add_argument("--head", choices=list(HEADS), default="svr-rbf")
    ap.add_argument("--backbone", choices=list(BACKBONE_NAMES), default="small")
    ap.add_argument("--out", default="rqi_model.joblib",
                    help="artifact filename under ml/cache/ (use a side name to "
                         "build a gate candidate without clobbering the champion)")
    args = ap.parse_args()

    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X_all = build_features(args.recipe, args.backbone)
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    X, df = X_all[keep], df[keep].reset_index(drop=True)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    is_bad = (yc >= BAD_FROM).astype(int)

    # ---- honest SPATIAL CV pass: metrics + OOF predictions for calibration ----
    coords = S.load_coords(df["image_filename"])
    groups = S.grid_cells(coords["lat"].values, coords["lon"].values)
    res = S.nested_spatial_cv(X, y, yc, groups, HEADS[args.head])
    oof, yp = res["oof"], res["pred"]
    m = S.ordinal_metrics(yc, yp, oof)
    cv = {
        "protocol": f"spatial {S.N_SPLITS}-fold StratifiedGroupKFold, "
                    f"{S.CELL_M} m cells, seed {S.SEED}, nested cut-points",
        "mae": m["mae"],
        "exact_acc": m["exact"],
        "off_by_one_acc": m["off1"],
        "qwk": m["qwk"],
        "bad_road_acc": m["bad_acc"],
        "bad_road_auc": m["bad_auc"],
    }

    # deployed cut-points: tuned on the pooled spatial OOF predictions
    thresholds = tune_thresholds(yc, oof)

    # ---- P(bad) calibration on OOF scores ----
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(oof, is_bad)

    # ---- reliability: when model says k, what is true class distribution ----
    reliability = {}
    for k in range(RQI_MIN, RQI_MAX + 1):
        sel = yp == k
        if sel.sum() == 0:
            continue
        dist = {int(c): float(np.mean(yc[sel] == c))
                for c in range(RQI_MIN, RQI_MAX + 1)}
        reliability[int(k)] = {"n": int(sel.sum()), "true_dist": dist}

    # ---- final fit on 100% ----
    pipe = make_pipeline(StandardScaler(), HEADS[args.head]())
    pipe.fit(X, y)

    keys, needs_clip = RECIPES[args.recipe]
    recipe_spec = {"name": args.recipe, "keys": keys, "needs_clip": needs_clip,
                   "crop_top": 0.35}
    views = hires_views_for(keys)
    if views:
        recipe_spec["hires_views"] = {v: HIRES_VIEWS[v] for v in views}
    artifact = {
        "version": 2,
        "pipeline": pipe,
        "p_bad_calibrator": iso,
        "backbone": BACKBONE_NAMES[args.backbone],
        "feature_recipe": recipe_spec,
        "head": args.head,
        "thresholds": thresholds,
        "rqi_clip": [RQI_MIN, RQI_MAX],
        "bad_from": BAD_FROM,
        "road_prob_min": ROAD_PROB_MIN,
        "n_train": int(len(df)),
        "scale_meaning": "1=excellent .. 4=poor (lower=better road)",
        "cv_metrics": cv,
        "reliability": reliability,
    }
    out = os.path.join(CACHE, args.out)
    joblib.dump(artifact, out)
    print(f"Trained on {len(df)} images -> {out}")
    print(json.dumps({k: v for k, v in artifact.items()
                      if k not in ("pipeline", "p_bad_calibrator")}, indent=2))


if __name__ == "__main__":
    main()
