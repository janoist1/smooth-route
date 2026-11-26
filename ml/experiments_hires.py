#!/usr/bin/env python3
"""
Era 8 evaluation: do higher-resolution road-region features (and YOLO damage
evidence) beat the live champion on the OFFICIAL spatial CV?

Every candidate runs through ml/spatial_cv.nested_spatial_cv (1 km grid cells,
StratifiedGroupKFold 5, seed 42, nested cut-points) on the same images as the
gate, and is compared PAIRED against the champion recipe (DINOv2-small
cls+patch at 224 px, StandardScaler + SVR-RBF C=1 eps=0.05) with the cell
bootstrap of ml/spatial_cv.paired_bootstrap_delta. Besides the headline
metrics it reports where the champion is weak: class-2 recall and
Budapest-only QWK / AUC (same OOF predictions, filtered).

Because the grid holds dozens of cells, the best one is optimistically biased
(winner's curse). `--shifts K` re-runs the top candidates paired against the
champion on K randomly shifted grids (same perturbation as era 6).

Inputs (ml/cache/, gitignored):
  dataset_v2.csv, feats_v2_<bb>.npz              (champion features)
  feats_hires_<bb>_<view>.npz                    (ml/extract_features_hires.py)
  yolo_feats.npz                                 (ml/extract_yolo_features.py)

Heads: svr (= champion head), svravg (score average of a champion-feature SVR
and an SVR on the extra block, see BlockSVRAvg), svr3, ridge.

Usage (PY=/Users/i/Dev/smooth-route/.venv/bin/python):
  $PY ml/experiments_hires.py                         # full grid, small + base
  $PY ml/experiments_hires.py --views road50 --backbones small --heads svr,svravg
  $PY ml/experiments_hires.py --only yolo --heads svr,svravg,ridge  # experiment 2
  $PY ml/experiments_hires.py --only "champ+road50 mean"  # substring filter
  # winner's-curse check of exact candidate@head pairs on 6 shifted grids:
  $PY ml/experiments_hires.py --shifts 6 \
      --pairs "champ+full mean+std@svravg;full cls+allmean+roadmean@svr"
Writes ml/cache/experiments_hires*.csv (gitignored; one row per cand x head).
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import RidgeCV
from sklearn.metrics import recall_score
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402

warnings.filterwarnings("ignore")
CACHE = os.path.join(S.ROOT, "ml", "cache")
DROP_RQI5, ROAD_PROB_MIN = True, 0.55   # same filter as the gate


class BlockSVRAvg(BaseEstimator, RegressorMixin):
    """Average of two SVR-RBF heads, one per column block ([:split], [split:]).

    For "champ+X" candidates the first 768 columns are the champion features,
    so this is a score-level ensemble of the champion and an X-only head
    (each with its own gamma='scale'), instead of one RBF over the concat.
    """

    def __init__(self, split=768, C=1.0, epsilon=0.05):
        self.split, self.C, self.epsilon = split, C, epsilon

    def fit(self, X, y):
        mk = lambda: SVR(C=self.C, gamma="scale", epsilon=self.epsilon)  # noqa: E731
        self.a_ = mk().fit(X[:, :self.split], y)
        self.b_ = mk().fit(X[:, self.split:], y)
        return self

    def predict(self, X):
        return (self.a_.predict(X[:, :self.split])
                + self.b_.predict(X[:, self.split:])) / 2


HEADS = {
    "svravg": lambda: BlockSVRAvg(split=768),
    "svr": lambda: SVR(C=1.0, gamma="scale", epsilon=0.05),   # champion head
    "svr3": lambda: SVR(C=3.0, gamma="scale", epsilon=0.05),
    "ridge": lambda: RidgeCV(alphas=[1, 3, 10, 30, 100, 300, 1000, 3000, 10000]),
}
ALL_VIEWS = ["road50lo", "road50", "road50x15", "roadc2x", "fulllo", "full"]


def load_base():
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    keep = df["is_road_prob"].values >= ROAD_PROB_MIN
    if DROP_RQI5:
        keep &= df["rqi"].values != 5
    return df, keep


def load_npz(path, files):
    z = np.load(path, allow_pickle=True)
    if "files" in z.files:
        assert list(z["files"]) == list(files), f"{path} misaligned with manifest"
    return z


def candidates(df, keep, views, backbones):
    """name -> feature matrix (already filtered with `keep`)."""
    files = df["image_filename"].values
    out = {}
    pools = {}
    for bb in backbones:
        F = load_npz(os.path.join(CACHE, f"feats_v2_{bb}.npz"), files)
        tag = "" if bb == "small" else f"[{bb}] "
        pools[bb] = {"cls": F["cls"][keep], "patch": F["patch"][keep],
                     "patch_crop": F["patch_crop"][keep]}
        champ = np.hstack([pools[bb]["cls"], pools[bb]["patch"]])
        out[f"{tag}champ (cls+patch @224)"] = champ
        if bb == "small":
            # low-res road control that already exists in the v2 cache
            out["champ+patch_crop @224 (control)"] = np.hstack(
                [champ, pools[bb]["patch_crop"]])
        for v in views:
            p = os.path.join(CACHE, f"feats_hires_{bb}_{v}.npz")
            if not os.path.exists(p):
                continue
            H = load_npz(p, files)
            g = lambda k: H[f"{v}_{k}"][keep]  # noqa: E731
            out[f"{tag}{v} cls+mean"] = np.hstack([g("cls"), g("mean")])
            out[f"{tag}{v} mean+std"] = np.hstack([g("mean"), g("std")])
            out[f"{tag}champ+{v} mean"] = np.hstack([champ, g("mean")])
            out[f"{tag}champ+{v} cls+mean"] = np.hstack([champ, g("cls"), g("mean")])
            out[f"{tag}champ+{v} gem"] = np.hstack([champ, g("gem")])
            out[f"{tag}champ+{v} lc"] = np.hstack([champ, g("lc")])
            out[f"{tag}champ+{v} mean+std"] = np.hstack([champ, g("mean"), g("std")])
            out[f"{tag}champ+{v} sp"] = np.hstack([champ, g("sp")])
            out[f"{tag}champ+{v} mid"] = np.hstack([champ, g("midmean"), g("midstd")])
            if v.startswith("full"):
                # one hi-res pass replacing the 224 pass entirely
                out[f"{tag}{v} cls+allmean"] = np.hstack([g("cls"), g("allmean")])
                out[f"{tag}{v} cls+allmean+roadmean"] = np.hstack(
                    [g("cls"), g("allmean"), g("mean")])
                out[f"{tag}{v} cls+allmean+roadmean+mid"] = np.hstack(
                    [g("cls"), g("allmean"), g("mean"), g("midmean"), g("midstd")])
                out[f"{tag}champ+{v} cls+allmean+roadmean"] = np.hstack(
                    [champ, g("cls"), g("allmean"), g("mean")])
    yp = os.path.join(CACHE, "yolo_feats.npz")
    if os.path.exists(yp) and "small" in pools:
        Y = load_npz(yp, files)
        names = [str(n) for n in Y["names"]]
        champ = np.hstack([pools["small"]["cls"], pools["small"]["patch"]])
        # counts/areas are heavy-tailed: log-compress (areas are fractions)
        yx = np.log1p(np.clip(Y["X"][keep].astype(np.float64), 0, None) * 100)
        sel = {
            "all": [True] * len(names),
            "roi": ["__roi__" in n for n in names],
            "any": ["__any__" in n for n in names],
        }
        for k, m in sel.items():
            m = np.array(m)
            out[f"yolo {k} only"] = yx[:, m]
            out[f"champ+yolo {k}"] = np.hstack([champ, yx[:, m]])
    return out


def champ_width(name):
    """Width of the leading champion block of a "champ+..." candidate."""
    if "champ+" not in name:
        return None
    return 1536 if name.startswith("[base]") else 768


def run(X, y, yc, groups, head, name=""):
    if head == "svravg":
        split = champ_width(name)
        return S.nested_spatial_cv(X, y, yc, groups,
                                   lambda: BlockSVRAvg(split=split))
    return S.nested_spatial_cv(X, y, yc, groups, HEADS[head])


def report(yc, res, area):
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    rec = recall_score(yc, res["pred"], labels=S.RQI_LABELS, average=None,
                       zero_division=0)
    m.update({f"rec{c}": float(r) for c, r in zip(S.RQI_LABELS, rec)})
    b = area == "budapest"
    mb = S.ordinal_metrics(yc[b], res["pred"][b], res["oof"][b])
    m.update({"bp_qwk": mb["qwk"], "bp_mae": mb["mae"], "bp_auc": mb["bad_auc"]})
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--views", default=",".join(ALL_VIEWS))
    ap.add_argument("--backbones", default="small,base")
    ap.add_argument("--heads", default="svr,ridge")
    ap.add_argument("--only", default="", help="comma-separated substrings")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--shifts", type=int, default=0,
                    help="re-check the top candidates on K shifted grids")
    ap.add_argument("--pairs", default="",
                    help='exact "candidate@head" list separated by ";" '
                         "(overrides --only/--heads; all go to the shift check)")
    ap.add_argument("--out", default="experiments_hires.csv",
                    help="file name under ml/cache/ (keep the experiments_* "
                         "prefix so it stays gitignored)")
    args = ap.parse_args()

    df, keep = load_base()
    bbs = [b for b in args.backbones.split(",")
           if os.path.exists(os.path.join(CACHE, f"feats_v2_{b}.npz"))]
    cands = candidates(df, keep, args.views.split(","), bbs)
    pairs = [tuple(p.rsplit("@", 1)) for p in args.pairs.split(";") if p.strip()]
    if pairs:
        missing = [c for c, _ in pairs if c not in cands]
        assert not missing, f"unknown candidates: {missing}"
        cands = {k: v for k, v in cands.items()
                 if k.startswith("champ (") or k in {c for c, _ in pairs}}
        args.top = len(pairs)
        args.heads = ",".join(sorted({h for _, h in pairs} | {"svr"}))
    if args.only:
        subs = [s.strip() for s in args.only.split(",")]
        cands = {k: v for k, v in cands.items()
                 if k.startswith("champ (") or any(s in k for s in subs)}
    d = df[keep].reset_index(drop=True)
    y = d["manual_rqi"].values.astype(float)
    yc = d["rqi"].values.astype(int)
    coords = S.load_coords(d["image_filename"])
    area = coords["area"].values
    lat, lon = coords["lat"].values, coords["lon"].values
    groups = S.grid_cells(lat, lon)
    print(f"n={len(d)} images, {len(np.unique(groups))} cells, "
          f"{len(cands)} feature sets x heads {args.heads}\n")

    ref = run(cands["champ (cls+patch @224)"], y, yc, groups, "svr")
    rows, results = [], {}
    for name, X in cands.items():
        for head in args.heads.split(","):
            if pairs and (name, head) not in pairs and not (
                    name.startswith("champ (") and head == "svr"):
                continue
            if head == "svravg" and champ_width(name) is None:
                continue
            if name.startswith("champ (") and head == "svr":
                res = ref
            else:
                res = run(X, y, yc, groups, head, name)
            m = report(yc, res, area)
            dl = S.paired_bootstrap_delta(yc, ref, res, groups)
            m.update({"dqwk": dl["qwk"][0], "dqwk_lo": dl["qwk"][1],
                      "dqwk_hi": dl["qwk"][2], "dmae": dl["mae"][0],
                      "dmae_hi": dl["mae"][2], "dauc": dl["bad_auc"][0],
                      "dauc_lo": dl["bad_auc"][1], "dim": X.shape[1]})
            results[(name, head)] = res
            rows.append({"cand": name, "head": head, **m})
            print(f"{name:42s} {head:5s} d={X.shape[1]:>5} QWK={m['qwk']:.3f} "
                  f"MAE={m['mae']:.3f} AUC={m['bad_auc']:.3f} rec2={m['rec2']:.2f} "
                  f"| BP QWK={m['bp_qwk']:.3f} AUC={m['bp_auc']:.3f} "
                  f"| ΔQWK {m['dqwk']:+.3f} [{m['dqwk_lo']:+.3f},{m['dqwk_hi']:+.3f}]"
                  f" ΔMAE {m['dmae']:+.3f} ΔAUC {m['dauc']:+.3f}"
                  f"{'  *' if m['dqwk_lo'] > 0 else ''}", flush=True)

    out = os.path.join(CACHE, args.out)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved -> {os.path.relpath(out, S.ROOT)}")

    if args.shifts:
        top = sorted((r for r in rows if not r["cand"].startswith("champ (")),
                     key=lambda r: -r["qwk"])[:args.top]
        if pairs:
            top = [r for r in rows if (r["cand"], r["head"]) in pairs]
        rng = np.random.default_rng(S.SEED)
        offs = [tuple(rng.uniform(0, 1, 2)) for _ in range(args.shifts)]
        print(f"\nWinner's-curse check: top {len(top)} on {len(offs)} shifted grids "
              f"(paired ΔQWK vs champion; * = CI > 0)")
        grids = [S.grid_cells(lat, lon, offset=off) for off in offs]
        champs = [run(cands["champ (cls+patch @224)"], y, yc, g, "svr")
                  for g in grids]
        for r in top:
            X = cands[r["cand"]]
            ds, sig = [], 0
            for g, rr in zip(grids, champs):
                rn = run(X, y, yc, g, r["head"], r["cand"])
                dl = S.paired_bootstrap_delta(yc, rr, rn, g)
                ds.append(dl["qwk"][0])
                sig += dl["qwk"][1] > 0
            print(f"  {r['cand']:42s} {r['head']:5s} ΔQWK per shift "
                  + " ".join(f"{v:+.3f}" for v in ds)
                  + f" | mean {np.mean(ds):+.3f}, CI>0 in {sig}/{len(offs)}",
                  flush=True)


if __name__ == "__main__":
    main()
