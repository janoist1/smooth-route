#!/usr/bin/env python3
"""
Is any challenger MEASURABLY better than the live champion on the spatial CV?

The experiment grid picks its best cell out of ~100 — the top number is
optimistically biased (winner's curse) and the CV's 95% CI is about ±0.07 QWK.
This script compares the top grid cells (and the fine-tune OOF, if present)
against the champion PAIRED — same folds, same images — with a cell-level
bootstrap of the difference. A challenger is "measurably better" only if the
95% CI of ΔQWK excludes zero.

Usage:  .venv/bin/python ml/compare_candidates.py
"""
import os
import sys

import numpy as np
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from experiments import load, variants  # noqa: E402
from heads import OrdinalLogistic  # noqa: E402

CACHE = os.path.join(S.ROOT, "ml", "cache")

CANDIDATES = [
    # (backbone, feature variant, head name, factory)
    ("small", "cls+patch", "svr C=1 (CHAMPION)",
     lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)),
    ("small", "cls+patch flipavg", "svr C=1",
     lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)),
    ("small", "cls+patch+crop", "ordlogit", lambda: OrdinalLogistic(alpha=300.0)),
    ("small", "all", "ordlogit", lambda: OrdinalLogistic(alpha=300.0)),
    ("base", "cls+patch", "svr C=1",
     lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)),
    ("base", "all", "ordlogit", lambda: OrdinalLogistic(alpha=300.0)),
]


def main():
    cache = {}
    ref = None
    rows = []
    for bb, var, hname, fn in CANDIDATES:
        if bb not in cache:
            cache[bb] = load(bb)
        feats, df = cache[bb]
        y = df["manual_rqi"].values.astype(float)
        yc = df["rqi"].values.astype(int)
        c = S.load_coords(df["image_filename"])
        groups = S.grid_cells(c["lat"].values, c["lon"].values)
        res = S.nested_spatial_cv(variants(feats)[var], y, yc, groups, fn)
        if ref is None:
            ref, ref_files = res, list(df["image_filename"])
        rows.append((f"{bb:6s} {var:18s} {hname}", res))

    ft = os.path.join(CACHE, "oof_ft2.npz")
    if os.path.exists(ft):
        z = np.load(ft, allow_pickle=True)
        assert list(z["files"]) == ref_files, "fine-tune OOF misaligned"
        rows.append(("small  finetune last 2 blocks  linear",
                     {"oof": z["oof"], "pred": z["pred"], "fold": z["fold"]}))

    print(f"Paired vs champion, spatial CV ({S.CELL_M} m cells, seed {S.SEED}), "
          f"95% cell-bootstrap CI of the difference\n")
    for name, res in rows:
        m = S.ordinal_metrics(yc, res["pred"], res["oof"])
        d = S.paired_bootstrap_delta(yc, ref, res, groups)
        sig = "YES" if d["qwk"][1] > 0 else "no"
        print(f"{name:45s} QWK={m['qwk']:.3f} MAE={m['mae']:.3f} "
              f"AUC={m['bad_auc']:.3f} | ΔQWK {d['qwk'][0]:+.3f} "
              f"[{d['qwk'][1]:+.3f},{d['qwk'][2]:+.3f}]  ΔMAE {d['mae'][0]:+.3f} "
              f"[{d['mae'][1]:+.3f},{d['mae'][2]:+.3f}]  ΔAUC {d['bad_auc'][0]:+.3f} "
              f"[{d['bad_auc'][1]:+.3f},{d['bad_auc'][2]:+.3f}]  better: {sig}")


if __name__ == "__main__":
    main()
