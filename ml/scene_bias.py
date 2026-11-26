#!/usr/bin/env python3
"""
T-43: where the champion goes wrong in Budapest, and two cheap fixes for the
"reads the scene, not the road" bias, under the official protocol.

Analysis (``analyse``): the champion's spatial out-of-fold predictions
(ml/cache/oof_spatial_champion.csv) joined with the Era 9 VLM scene/defect
attributes (ml/cache/vlm_attributes.csv): signed error by area, road type and
attribute, and class separation *within* each road type. "Budapest" is
reported two ways: the collection area (VII–VIII. district, 229 frames) and
the city bounding box (+ a 1.4 km M1/M7 stretch at Budaörs, 361 frames).

Fixes tested (``eval``), each paired against the champion on identical folds
(ml/external_data.run_cv: spatial 1 km cells, leave-one-area-out, Budapest
bounding box held out; nested cut-points on our training labels):
  focal   champion features + a second view of the road just ahead: the
          StreetSurfaceVis focal crop (x 25-75 %, y 50-100 % of the frame)
          through the champion extractor (servable like Era 8's hi-res view)
  rtbal   training-time weights that give every road type the same class mix
          (w = P(class) / P(class | road type), from the training rows only;
          road type = the stored VLM attribute, needed only for training)

Usage: /Users/i/Dev/smooth-route/.venv/bin/python -I ml/scene_bias.py analyse|extract|eval
Result (2026-11-26): docs/MODEL_EXPERIMENTS.md "Era 16".
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import external_data as X  # noqa: E402
import spatial_cv as S  # noqa: E402

CACHE = X.CACHE
FOCAL_BOX = (0.25, 0.5, 0.75, 1.0)  # StreetSurfaceVis' recommended focal crop
FOCAL_FEATS = os.path.join(CACHE, "feats_v2_small_focal.npz")
OUT_JSON = os.path.join(CACHE, "scene_bias_results.json")


def joined():
    o = pd.read_csv(os.path.join(CACHE, "oof_spatial_champion.csv"))
    a = pd.read_csv(os.path.join(CACHE, "vlm_attributes.csv"))
    d = o.merge(a, on="image_filename", how="left")
    d["serr"] = d["score"] - d["human_rqi"]
    d["err"] = d["pred_rqi"] - d["human_rqi"]
    d["bbox"] = (d["lat"].between(*X.BP_BBOX["lat"]) & d["lon"].between(*X.BP_BBOX["lon"]))
    return d


def cmd_analyse():
    from scipy.stats import spearmanr
    d = joined()
    for name, s in (("Budapest area (VII-VIII.)", d["area"] == "budapest"),
                    ("Budapest bounding box", d["bbox"]),
                    ("  of which M1/M7 Budaörs", d["bbox"] & (d["area"] != "budapest")),
                    ("rest", ~d["bbox"])):
        x = d[s]
        print(f"\n== {name}: n={len(x)} bias {x['serr'].mean():+.2f}; predicted better "
              f"than the owner {np.mean(x['err'] < 0):.0%}, worse {np.mean(x['err'] > 0):.0%}")
        print(pd.crosstab(x["human_rqi"], x["pred_rqi"]).to_string())
    print("\n== within road type (VLM attribute): separation and bias per owner class")
    for rt, x in d.groupby("road_type"):
        if len(x) < 30:
            continue
        m = S.ordinal_metrics(x["human_rqi"].values, x["pred_rqi"].values, x["score"].values)
        bias = x.groupby("human_rqi")["serr"].mean().round(2).to_dict()
        areas = x["area"].value_counts().to_dict()
        print(f"  {rt:18s} n={len(x):4d} QWK {m['qwk']:.3f} rho "
              f"{spearmanr(x['human_rqi'], x['score']).statistic:.3f} bias by class {bias} "
              f"areas {areas}")


def cmd_extract():
    """Focal-crop view of our labelled frames through the champion extractor."""
    from PIL import Image
    from extract_features_v2 import find_image
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    tmp = os.path.join(X.ROOT, "data", "cache", "focal_frames")  # gitignored
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for f in df["image_filename"]:
        out = os.path.join(tmp, f)
        if not os.path.exists(out):
            im = Image.open(find_image(f)).convert("RGB")
            w, h = im.size
            box = (round(FOCAL_BOX[0] * w), round(FOCAL_BOX[1] * h),
                   round(FOCAL_BOX[2] * w), round(FOCAL_BOX[3] * h))
            im.crop(box).save(out, quality=95)
        paths.append(out)
    feats = X._champion_extract(paths)
    np.savez_compressed(FOCAL_FEATS, files=df["image_filename"].values,
                        box=np.array(FOCAL_BOX), **feats)
    print(f"saved {FOCAL_FEATS} {feats['cls'].shape}")


def road_type_weights(lab, road_type):
    """callable(train_idx) -> w = P(class) / P(class | road type), clipped."""
    def fn(tr):
        yc, rt = lab["yc"][tr], road_type[tr]
        p = pd.Series(yc).value_counts(normalize=True)
        cond = pd.crosstab(rt, yc, normalize="index")
        w = np.array([p[c] / max(cond.loc[r, c], 1e-3) for r, c in zip(rt, yc)])
        w = np.clip(w, 0.2, 5.0)
        return w / w.mean()
    return fn


def cmd_eval(args):
    lab = X.load_ours()
    z = np.load(FOCAL_FEATS, allow_pickle=True)
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    if list(z["files"]) != list(df["image_filename"]):
        raise ValueError("focal features misaligned with dataset_v2.csv")
    Xf = np.hstack([z["cls"], z["patch"]])[lab["keep"]]
    att = pd.read_csv(os.path.join(CACHE, "vlm_attributes.csv")).set_index("image_filename")
    rt = att.reindex(lab["files"])["road_type"].fillna("other").values
    plan = [("champion", {}),
            ("focal view only", {"X": Xf}),
            ("champion + focal view", {"X": np.hstack([lab["X"], Xf])}),
            ("road-type balanced weights", {"ours_weight": road_type_weights(lab, rt)})]
    rows, refs = [], {}
    for kind in ("spatial", "loro", "bp_bbox"):
        for name, kw in plan:
            res = X.run_cv(lab, kind, n_jobs=args.jobs, **kw)
            if name == "champion":
                refs[kind] = res
            row = X.summarise(name, kind, lab, res, None if name == "champion" else refs[kind])
            # per road type QWK on this protocol's test frames
            te = np.zeros(len(lab["y"]), bool)
            te[res["test"]] = True
            for r in ("motorway", "urban_main", "urban_residential", "rural_road"):
                s = te & (rt == r)
                if s.sum() >= 30:
                    row[f"rt_{r}"] = S.ordinal_metrics(lab["yc"][s], res["pred"][s],
                                                       res["oof"][s])["qwk"]
            print("          within road type QWK: " + "  ".join(
                f"{k[3:]} {v:.3f}" for k, v in row.items() if k.startswith("rt_")))
            rows.append(row)
            json.dump({"rows": rows}, open(OUT_JSON, "w"), default=X._json, indent=1)
    print(f"saved {OUT_JSON}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["analyse", "extract", "eval"])
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    {"analyse": cmd_analyse, "extract": cmd_extract,
     "eval": lambda: cmd_eval(args)}[args.cmd]()


if __name__ == "__main__":
    main()
