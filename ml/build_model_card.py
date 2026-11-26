#!/usr/bin/env python3
"""
Write ml/model_card.json: the HONEST metrics of the live RQI artifact.

The live artifact's own ``cv_metrics`` still carry the old random-CV numbers
(QWK 0.895, spatially leaky). Re-saving the champion would also re-tune its
cut-points and P(bad) calibrator, so instead this small committed sidecar
holds the spatial numbers, keyed by the artifact's sha256. The backend
(app/services/model_card.py) shows them on the model card only while the
hash matches the live file; a different artifact falls back to its own
``cv_metrics``.

Numbers (same code paths as the gate and Era 7):
  frame      champion OOF on the official spatial protocol
             (ml/segment_eval.champion_oof: 1 km cells, StratifiedGroupKFold 5,
             seed 42, nested cut-points) - equals ml/evaluate_artifact.py
  segment    200 m segments, median score, nested cut-points, averaged over
             the 3 cut phases (ml/segment_eval.evaluate; Era 7)
  new_area   leave-one-area-out, pooled over the 4 collection areas
             (train on 3, test on the 4th; as in ml/spatial_analysis.py)

Usage: /Users/i/Dev/smooth-route/.venv/bin/python ml/build_model_card.py   (~1 min)
"""
import datetime as dt
import hashlib
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segment_eval as E  # noqa: E402
import spatial_cv as S  # noqa: E402
from save_model_v2 import HEADS, build_features  # noqa: E402

OUT = os.path.join(S.ROOT, "ml", "model_card.json")
SEGMENT_LENGTH_M = 200
KIND = "median_score"


def sha256_12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def rounded(m, keys=("qwk", "mae", "exact", "off1", "bad_acc", "bad_auc")):
    return {k: round(float(m[k]), 3) for k in keys if k in m}


def leave_area_out(fr):
    """Pooled leave-one-area-out metrics of the champion recipe."""
    df = pd.read_csv(os.path.join(E.CACHE, "dataset_v2.csv")).set_index("image_filename")
    X_all = build_features(E.CHAMPION["recipe"], E.CHAMPION["backbone"])
    X = X_all[df.index.get_indexer(fr["image_filename"])]
    y = df.loc[fr["image_filename"], "manual_rqi"].values.astype(float)
    yc, area = fr["human_rqi"].values, fr["area"].values
    g1k = S.grid_cells(fr["lat"].values, fr["lon"].values)
    head = HEADS[E.CHAMPION["head"]]
    pred, score = np.zeros(len(y), int), np.zeros(len(y))
    for a in S.AREA_LABELS:
        te, tr = area == a, area != a
        score[te] = S._fit_predict(head, X[tr], y[tr], X[te])
        ioof = np.zeros(tr.sum())
        for itr, ite in S.spatial_folds(yc[tr], g1k[tr], S.INNER_SPLITS, S.SEED):
            ioof[ite] = S._fit_predict(head, X[tr][itr], y[tr][itr], X[tr][ite])
        pred[te] = np.digitize(score[te], S.tune_thresholds(yc[tr], ioof)) + 1
    return S.ordinal_metrics(yc, pred, score)


def main():
    art = joblib.load(E.ARTIFACT)
    fr, inner, inner_p, _ = E.champion_oof()
    frame = S.ordinal_metrics(fr["human_rqi"].values, fr["pred_rqi"].values,
                              fr["score"].values)

    chain, pos, fp, rank = E.build_chains(fr)
    segsets = []
    for ph in E.PHASES:
        seg = E.cut_segments(chain, fp, rank, SEGMENT_LENGTH_M, ph)
        segsets.append((seg, E.segment_table(seg, fr, fp)))
    runs = E.evaluate(fr, inner, inner_p, segsets, KIND)["runs"]
    segment = {k: float(np.mean([r["m"][k] for r in runs]))
               for k in ("qwk", "mae", "exact", "bad_auc")}

    new_area = leave_area_out(fr)
    card = {
        "artifact_sha256_12": sha256_12(E.ARTIFACT),
        "measured_on": dt.date.today().isoformat(),
        "protocol": f"spatial CV: {S.CELL_M} m grid cells, StratifiedGroupKFold "
                    f"{S.N_SPLITS}, seed {S.SEED}, nested cut-points",
        "n_train": int(art.get("n_train", len(fr))),
        "frame": rounded(frame),
        "segment": {"length_m": SEGMENT_LENGTH_M, "aggregator": KIND,
                    **rounded(segment)},
        "new_area": {"protocol": "leave-one-area-out (4 areas), pooled",
                     **rounded(new_area)},
        "generated_by": "ml/build_model_card.py",
    }
    with open(OUT, "w") as f:
        json.dump(card, f, indent=2)
        f.write("\n")
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
