#!/usr/bin/env python3
"""
Era 16 (T-58): StreetSurfaceVis as external training data for the RQI model.

Dataset: SurfaceAI StreetSurfaceVis v1.0 (HTW Berlin, Zenodo record 11449977,
CC BY-SA 4.0; Mapillary images): 9,122 street-level images from Germany with
surface type (asphalt, concrete, paving_stones, sett, unpaved) and surface
quality in the OSM ``smoothness`` vocabulary (excellent ... very_bad) for the
focal area (the centre of the lower image half). We use the 256 px wide copies
(``s_256.zip``, 99 MB; the next size is 1.3 GB). Files live in the gitignored
``data/external/streetsurfacevis/`` and are never committed; attribution in
docs/IMAGERY_SOURCES.md.

Label mapping: OSM smoothness word -> our level *key* (``OSM_TO_KEY``) -> value
and severity through ml/rqi_scale.py, so no level number is written here.

Subcommands
  extract       champion features for the external images: the exact
                extract_features_v2.extract_dinov2 (dinov2-small, its HF
                processor = resize 256 + centre crop 224, CLS + patch mean)
                -> ml/cache/feats_ext_ssv_small.npz + ext_ssv_manifest.csv
  extract-w256  the same for OUR labelled frames downscaled to 256 px width
                (diagnostic: what does the low resolution alone cost?)
                -> ml/cache/feats_v2_small_w256.npz
  eval          the experiments, paired against the champion on identical folds

Protocol (ml/spatial_cv.py): 1 km cells, StratifiedGroupKFold 5, seed 42, plus
leave-one-area-out (LORO) and a Budapest hold-out; cut-points are always tuned
on inner spatial OOF of OUR training labels. External rows are appended to
every training fit (outer and inner) and are never scored, so no test label
or test image is touched.

Usage (main checkout interpreter; -I because it reads downloaded files):
  /Users/i/Dev/smooth-route/.venv/bin/python -I ml/external_data.py extract
  /Users/i/Dev/smooth-route/.venv/bin/python -I ml/external_data.py eval [--quick]
Result (2026-11-26): see docs/MODEL_EXPERIMENTS.md "Era 16".
"""
import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rqi_scale as R  # noqa: E402
import spatial_cv as S  # noqa: E402

warnings.filterwarnings("ignore")
ROOT = S.ROOT
CACHE = os.environ.get("RQI_ML_CACHE") or os.path.join(ROOT, "ml", "cache")
EXT_DIR = os.path.join(ROOT, "data", "external", "streetsurfacevis")
EXT_CSV = os.path.join(EXT_DIR, "streetSurfaceVis_v1_0.csv")
EXT_IMG = os.path.join(EXT_DIR, "s_256")
EXT_FEATS = os.path.join(CACHE, "feats_ext_ssv_small.npz")
EXT_MANIFEST = os.path.join(CACHE, "ext_ssv_manifest.csv")
W256_FEATS = os.path.join(CACHE, "feats_v2_small_w256.npz")
OUT_JSON = os.path.join(CACHE, "external_data_results.json")

# OSM smoothness word (StreetSurfaceVis surface_quality) -> our level key in
# shared/rqi_scale.json. Same wording on both sides except intermediate/fair.
OSM_TO_KEY = {"excellent": "excellent", "good": "good", "intermediate": "fair",
              "bad": "poor", "very_bad": "very_poor"}
SURFACE_SETS = {
    "asph": ("asphalt",),
    "asph+conc": ("asphalt", "concrete"),
    "paved": ("asphalt", "concrete", "paving_stones", "sett"),
    "all": ("asphalt", "concrete", "paving_stones", "sett", "unpaved"),
}
AREAS = list(S.AREA_LABELS)
# Budapest city bounding box (incl. the Budaörs edge of the Törökbálint area):
# the "361 Budapest labels" of Era 15 are the frames inside it.
BP_BBOX = {"lat": (47.35, 47.62), "lon": (18.92, 19.34)}


def osm_to_severity(word):
    """OSM smoothness word -> ML severity number (via the canonical scale)."""
    return int(R.SCALE.to_severity(R.SCALE.value_of(OSM_TO_KEY[word])))


# --------------------------------------------------------------------------
# extraction
def _champion_extract(paths):
    """The champion's extractor, unchanged (same model, processor, pooling)."""
    from extract_features_v2 import BACKBONES, extract_dinov2
    return extract_dinov2(paths, BACKBONES["small"])


def cmd_extract():
    from PIL import Image
    meta = pd.read_csv(EXT_CSV)
    meta["path"] = [os.path.join(EXT_IMG, f"{i}.jpg") for i in meta["mapillary_image_id"]]
    # two files in s_256.zip v1.0 are empty (0 bytes): skip unreadable images
    have = meta["path"].map(lambda p: os.path.exists(p) and os.path.getsize(p) > 0)
    print(f"external images on disk: {have.sum()} / {len(meta)}")
    meta = meta[have].reset_index(drop=True)
    sizes = [Image.open(p).size for p in meta["path"]]
    meta["width"], meta["height"] = zip(*sizes)
    meta["severity"] = meta["surface_quality"].map(osm_to_severity)
    t = time.time()
    feats = _champion_extract(list(meta["path"]))
    print(f"extracted in {time.time() - t:.0f} s")
    np.savez_compressed(EXT_FEATS, ids=meta["mapillary_image_id"].values, **feats)
    meta.drop(columns="path").to_csv(EXT_MANIFEST, index=False)
    print(f"saved {EXT_FEATS} {feats['cls'].shape} + {EXT_MANIFEST}")


def cmd_extract_w256():
    """Our labelled frames resized to 256 px width (LANCZOS), then the
    champion extractor — a diagnostic for the external set's resolution."""
    from PIL import Image
    from extract_features_v2 import find_image
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    tmp = os.path.join(ROOT, "data", "cache", "w256_frames")  # gitignored
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for f in df["image_filename"]:
        out = os.path.join(tmp, f)
        if not os.path.exists(out):
            im = Image.open(find_image(f)).convert("RGB")
            w, h = im.size
            im.resize((256, round(256 * h / w)), Image.LANCZOS).save(out, quality=90)
        paths.append(out)
    feats = _champion_extract(paths)
    np.savez_compressed(W256_FEATS, files=df["image_filename"].values, **feats)
    print(f"saved {W256_FEATS} {feats['cls'].shape}")


# --------------------------------------------------------------------------
# data
def load_ours():
    from save_model_v2 import DROP_RQI5, ROAD_PROB_MIN, build_features
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    X_all = build_features("cls+patch", "small")
    road = df["is_road_prob"].values >= ROAD_PROB_MIN
    dropped = np.isin(df["rqi"].values, S.DROPPED_LEVELS)
    keep = road & ~dropped if DROP_RQI5 else road
    sub = df[keep].reset_index(drop=True)
    c = S.load_coords(sub["image_filename"])
    lab = {"X": X_all[keep], "y": sub["manual_rqi"].values.astype(float),
           "yc": sub["rqi"].values.astype(int), "lat": c["lat"].values,
           "lon": c["lon"].values, "area": c["area"].values,
           "files": sub["image_filename"].values, "keep": keep}
    lab["groups"] = S.grid_cells(lab["lat"], lab["lon"])
    lab["bbox"] = (np.asarray(lab["lat"] >= BP_BBOX["lat"][0])
                   & (lab["lat"] <= BP_BBOX["lat"][1])
                   & (lab["lon"] >= BP_BBOX["lon"][0])
                   & (lab["lon"] <= BP_BBOX["lon"][1]))
    # frames on the dropped level (Nagyon rossz), for the level-1 check only
    lab["X_dropped"] = X_all[road & dropped]
    return lab


def load_ext():
    z = np.load(EXT_FEATS, allow_pickle=True)
    m = pd.read_csv(EXT_MANIFEST)
    if not np.array_equal(z["ids"], m["mapillary_image_id"].values):
        raise ValueError("external features and manifest are misaligned")
    return {"X": np.hstack([z["cls"], z["patch"]]), "y": m["severity"].values.astype(float),
            "surface": m["surface_type"].values, "quality": m["surface_quality"].values}


def ext_rows(E, surfaces, levels=None):
    s = np.isin(E["surface"], SURFACE_SETS[surfaces])
    if levels is not None:
        s &= np.isin(E["y"].astype(int), levels)
    return np.flatnonzero(s)


# --------------------------------------------------------------------------
# model + CV with external rows in every training fit
class Head:
    """Champion head (StandardScaler -> SVR-RBF C=1, eps 0.05) with optional
    per-row weights and an optional domain indicator column appended AFTER
    scaling (so its scale ``dom`` is the knob, 0 = no indicator)."""

    def __init__(self, dom=0.0):
        self.dom = dom

    def fit(self, X, y, w=None, d=None):
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVR
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        if self.dom:
            Z = np.hstack([Z, self.dom * (np.zeros(len(X)) if d is None else d)[:, None]])
        self.svr = SVR(C=1.0, gamma="scale", epsilon=0.05).fit(Z, y, sample_weight=w)
        return self

    def predict(self, X):
        Z = self.sc.transform(X)
        if self.dom:
            Z = np.hstack([Z, np.zeros((len(X), 1))])  # test frames are ours
        return self.svr.predict(Z)


def _fit_pred(Xtr, ytr, wtr, dtr, Xte, dom):
    return Head(dom).fit(Xtr, ytr, wtr, dtr).predict(Xte)


def make_folds(lab, kind):
    if kind == "spatial":
        return S.spatial_folds(lab["yc"], lab["groups"])
    if kind == "loro":
        return [(np.flatnonzero(lab["area"] != a), np.flatnonzero(lab["area"] == a))
                for a in AREAS]
    if kind == "cell3km":  # between 1 km cells and a whole area held out
        g3 = S.grid_cells(lab["lat"], lab["lon"], cell_m=3000)
        return S.spatial_folds(lab["yc"], g3)
    if kind == "bp_bbox":
        return [(np.flatnonzero(~lab["bbox"]), np.flatnonzero(lab["bbox"]))]
    raise ValueError(kind)


def run_cv(lab, kind, ext=None, ours_weight=1.0, dom=0.0, ext_only=False,
           recal=False, n_jobs=8, X=None, make_head=None):
    """Outer CV; ``ext`` = (Xe, ye, we) appended to every training fit.

    make_head: zero-arg factory of an sklearn regressor used instead of the
    champion head (our rows only; used by ml/motorway_vlm.py).

    ours_weight: scalar, or callable(train_idx) -> per-row weights computed
    from the training rows only (used by ml/scene_bias.py).

    ext_only: the head never sees our labels (transfer check); our training
    labels then only tune the cut-points, on that model's scores.
    recal: external targets replaced per fold by the mean score that an
    ours-only model (training fold only) gives the images of each external
    level — aligns the two label scales without touching the test fold.
    """
    from joblib import Parallel, delayed
    X = lab["X"] if X is None else X
    folds = make_folds(lab, kind)
    jobs = []  # (fold, inner index or -1, train idx (ours), test idx (ours))
    for k, (tr, te) in enumerate(folds):
        jobs.append((k, -1, tr, te))
        for j, (itr, ite) in enumerate(S.spatial_folds(lab["yc"][tr], lab["groups"][tr],
                                                       S.INNER_SPLITS)):
            jobs.append((k, j, tr[itr], tr[ite]))

    def targets(tr):
        if ext is None or not recal:
            return None if ext is None else ext[1]
        s = _fit_pred(X[tr], lab["y"][tr], None, None, ext[0], 0.0)
        lv = ext[1].astype(int)
        means = {v: s[lv == v].mean() for v in np.unique(lv)}
        # keep the external order monotone (isotonic on level means)
        from sklearn.isotonic import IsotonicRegression
        keys = sorted(means)
        iso = IsotonicRegression().fit(keys, [means[v] for v in keys])
        return iso.predict(lv.astype(float))

    def one(tr, te):
        if make_head is not None:
            return make_head().fit(X[tr], lab["y"][tr]).predict(X[te])
        if ext_only:
            return _fit_pred(ext[0], ext[1], ext[2], None, X[te], 0.0)
        wo = ours_weight(tr) if callable(ours_weight) else np.full(len(tr), ours_weight)
        Xa, ya, wa, da = X[tr], lab["y"][tr], wo, np.zeros(len(tr))
        if ext is not None:
            ye = targets(tr)
            Xa = np.vstack([Xa, ext[0]])
            ya = np.r_[ya, ye]
            wa = np.r_[wa, ext[2]]
            da = np.r_[da, np.ones(len(ext[1]))]
        return _fit_pred(Xa, ya, wa, da, X[te], dom)

    if ext_only:  # one external model scores everything; no per-fold refit needed
        score_all = _fit_pred(ext[0], ext[1], ext[2], None, X, 0.0)
        preds = [score_all[te] for (_, _, _, te) in jobs]
    else:
        preds = Parallel(n_jobs=n_jobs)(delayed(one)(tr, te) for (_, _, tr, te) in jobs)
    n = len(lab["y"])
    oof, pred, fold = np.zeros(n), np.zeros(n, int), np.zeros(n, int)
    ths = []
    for k, (tr, te) in enumerate(folds):
        outer = [p for (kk, j, _, _), p in zip(jobs, preds) if kk == k and j == -1][0]
        ioof = np.zeros(n)
        for (kk, j, _, ite), p in zip(jobs, preds):
            if kk == k and j >= 0:
                ioof[ite] = p
        th = S.tune_thresholds(lab["yc"][tr], ioof[tr])
        oof[te], fold[te] = outer, k
        pred[te] = np.digitize(outer, th) + 1
        ths.append(th)
    return {"oof": oof, "pred": pred, "fold": fold, "thresholds": ths,
            "test": np.concatenate([te for _, te in folds])}


# --------------------------------------------------------------------------
# reporting
def _sub(res, s):
    return {"oof": res["oof"][s], "pred": res["pred"][s]}


def summarise(name, kind, lab, res, ref):
    """Headline + Budapest metrics and paired cell-bootstrap Δ vs ``ref``."""
    from sklearn.metrics import recall_score
    from scipy.stats import spearmanr
    te = np.zeros(len(lab["y"]), bool)
    te[res["test"]] = True
    yc, g = lab["yc"][te], lab["groups"][te]
    m = S.ordinal_metrics(yc, res["pred"][te], res["oof"][te])
    m["spearman"] = float(spearmanr(lab["y"][te], res["oof"][te]).statistic)
    m["rec"] = {int(c): float(r) for c, r in zip(
        S.RQI_LABELS, recall_score(yc, res["pred"][te], labels=S.RQI_LABELS,
                                   average=None, zero_division=0))}
    m["bias"] = float(res["oof"][te].mean() - lab["y"][te].mean())
    row = {"name": name, "kind": kind, **m}
    if ref is not None:
        d = S.paired_bootstrap_delta(yc, _sub(ref, te), _sub(res, te), g)
        row.update({f"d_{k}": v for k, v in d.items()})
    for tag, s in (("bp", lab["area"] == "budapest"), ("bpbox", lab["bbox"])):
        s = s & te
        if s.sum() < 20:
            continue
        mb = S.ordinal_metrics(lab["yc"][s], res["pred"][s], res["oof"][s])
        row[f"{tag}_qwk"], row[f"{tag}_mae"] = mb["qwk"], mb["mae"]
        row[f"{tag}_auc"], row[f"{tag}_n"] = mb["bad_auc"], int(s.sum())
        row[f"{tag}_bias"] = float(res["oof"][s].mean() - lab["y"][s].mean())
        if ref is not None:
            db = S.paired_bootstrap_delta(lab["yc"][s], _sub(ref, s), _sub(res, s),
                                          lab["groups"][s])
            row[f"{tag}_d_qwk"] = db["qwk"]
    for a in AREAS if kind == "loro" else ():
        s = (lab["area"] == a) & te
        row[f"loro_{a}"] = S.ordinal_metrics(lab["yc"][s], res["pred"][s],
                                             res["oof"][s])["qwk"]
    dq = (f" Δ{row['d_qwk'][0]:+.3f} [{row['d_qwk'][1]:+.3f},{row['d_qwk'][2]:+.3f}]"
          f"{'*' if row['d_qwk'][1] > 0 else ''}" if "d_qwk" in row else "")
    bp = (f" | BP n={row['bp_n']} QWK {row['bp_qwk']:.3f} MAE {row['bp_mae']:.3f} "
          f"AUC {row['bp_auc']:.3f} bias {row['bp_bias']:+.2f}" if "bp_qwk" in row else "")
    print(f"[{kind:7s}] {name:40s} QWK {m['qwk']:.3f} MAE {m['mae']:.3f} "
          f"exact {m['exact']:.3f} AUC {m['bad_auc']:.3f} ρ {m['spearman']:.3f} "
          f"bias {m['bias']:+.2f}{dq}{bp}", flush=True)
    return row


def level1_check(lab, E, name, idx, w, res):
    """Can the model reach the dropped level (Nagyon rossz)? Scores of our
    dropped-level frames (model fitted on all our labels + external rows; they
    are never in training) vs the spatial-CV OOF scores of our worst trained
    level (Rossz) from ``res``. AUC 0.5 = indistinguishable."""
    from sklearn.metrics import roc_auc_score
    worst = S.RQI_LABELS[-1]
    Xa, ya, wa = lab["X"], lab["y"], np.ones(len(lab["y"]))
    if idx is not None:
        Xa = np.vstack([Xa, E["X"][idx]])
        ya = np.r_[ya, E["y"][idx]]
        wa = np.r_[wa, np.full(len(idx), w)]
    s_drop = Head().fit(Xa, ya, wa).predict(lab["X_dropped"])
    s_worst = res["oof"][lab["yc"] == worst]
    top_cut = float(np.mean([t[-1] for t in res["thresholds"]]))
    auc = roc_auc_score(np.r_[np.zeros(len(s_worst)), np.ones(len(s_drop))],
                        np.r_[s_worst, s_drop])
    print(f"[level-1] {name:30s} n_dropped={len(s_drop)} score dropped mean "
          f"{s_drop.mean():.2f} max {s_drop.max():.2f} | Rossz OOF mean "
          f"{s_worst.mean():.2f} | above top cut {top_cut:.2f}: "
          f"{(s_drop > top_cut).mean():.0%} | AUC Rossz vs Nagyon rossz {auc:.3f}")
    return {"name": name, "mean_dropped": float(s_drop.mean()),
            "max_dropped": float(s_drop.max()), "mean_worst_oof": float(s_worst.mean()),
            "share_above_top_cut": float((s_drop > top_cut).mean()), "auc": float(auc)}


def _json(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def cmd_eval(args):
    global OUT_JSON
    OUT_JSON = args.out or OUT_JSON
    lab = load_ours()
    E = load_ext()
    model_levels = S.RQI_LABELS
    print(f"ours: {len(lab['y'])} frames, {len(np.unique(lab['groups']))} cells; "
          f"Budapest area {int((lab['area'] == 'budapest').sum())}, bbox {int(lab['bbox'].sum())}")
    print("external:", pd.crosstab(E["surface"], E["y"].astype(int)).to_dict())
    kinds = (("spatial",) if args.quick else
             tuple(args.kinds.split(",")) if args.kinds else ("spatial", "loro", "bp_bbox"))
    rows, refs = [], {}

    def ext(surfaces, w, levels=model_levels):
        i = ext_rows(E, surfaces, levels)
        return E["X"][i], E["y"][i], np.full(len(i), w)

    plan = [("champion", {})]
    if args.only in (None, "weights"):
        for surf in ("asph+conc", "paved"):
            for w in (0.25, 0.5, 1.0):
                plan.append((f"+ext {surf} w={w}", {"ext": ext(surf, w)}))
    if args.only in (None, "variants"):
        plan += [
            ("+ext asph w=0.5", {"ext": ext("asph", 0.5)}),
            # indicator scale 20: adds 400 to a typical squared distance of
            # ~1500 between standardised 768-d vectors (kernel factor ~0.6)
            ("+ext asph+conc w=0.5 domain", {"ext": ext("asph+conc", 0.5), "dom": 20.0}),
            ("+ext asph+conc w=0.5 recal", {"ext": ext("asph+conc", 0.5), "recal": True}),
            ("+ext paved w=0.5 recal", {"ext": ext("paved", 0.5), "recal": True}),
            ("+ext all incl. very_bad w=0.5", {"ext": ext("all", 0.5, None)}),
            ("ext-only asph+conc (transfer)", {"ext": ext("asph+conc", 1.0), "ext_only": True}),
            ("ext-only paved (transfer)", {"ext": ext("paved", 1.0), "ext_only": True}),
        ]
    if args.names:
        keep = set(args.names.split(",")) | {"champion"}
        plan = [(n, kw) for n, kw in plan if n in keep]
    for kind in kinds:
        for name, kw in plan:
            t = time.time()
            res = run_cv(lab, kind, n_jobs=args.jobs, **kw)
            if name == "champion":
                refs[kind] = res
            row = summarise(name, kind, lab, res, None if name == "champion" else refs[kind])
            row["sec"] = round(time.time() - t)
            rows.append(row)
            json.dump({"rows": rows}, open(OUT_JSON, "w"), default=_json, indent=1)

    if args.only in (None, "level1", "variants"):
        i = ext_rows(E, "all", None)  # incl. very_bad (only on unpaved roads)
        res_v = run_cv(lab, "spatial", n_jobs=args.jobs, ext=(E["X"][i], E["y"][i],
                                                               np.full(len(i), 0.5)))
        ref = refs.get("spatial") or run_cv(lab, "spatial", n_jobs=args.jobs)
        lv = [level1_check(lab, E, "champion", None, 0, ref),
              level1_check(lab, E, "+ext all incl. very_bad w=0.5", i, 0.5, res_v)]
        json.dump({"rows": rows, "level1": lv}, open(OUT_JSON, "w"), default=_json, indent=1)
    print(f"\nsaved {OUT_JSON}")


def cmd_w256(args):
    """Resolution diagnostic on our own frames: hi-res vs 256 px features."""
    lab = load_ours()
    z = np.load(W256_FEATS, allow_pickle=True)
    df = pd.read_csv(os.path.join(CACHE, "dataset_v2.csv"))
    if list(z["files"]) != list(df["image_filename"]):
        raise ValueError("w256 features misaligned with dataset_v2.csv")
    Xlo = np.hstack([z["cls"], z["patch"]])[lab["keep"]]
    cos = (lab["X"] * Xlo).sum(1) / np.linalg.norm(lab["X"], axis=1) / np.linalg.norm(Xlo, axis=1)
    print(f"cosine(hi-res, 256 px) features: median {np.median(cos):.3f}, "
          f"p10 {np.percentile(cos, 10):.3f}")
    ref = run_cv(lab, "spatial", n_jobs=args.jobs)
    summarise("champion (hi-res train+test)", "spatial", lab, ref, None)
    lo = run_cv(lab, "spatial", n_jobs=args.jobs, X=Xlo)
    summarise("256 px train+test", "spatial", lab, lo, ref)
    # hi-res-trained heads (and their cut-points) scoring 256 px test frames
    shift = {"oof": ref["oof"].copy(), "pred": ref["pred"].copy(), "test": ref["test"]}
    for k, (tr, te) in enumerate(make_folds(lab, "spatial")):
        s = _fit_pred(lab["X"][tr], lab["y"][tr], None, None, Xlo[te], 0.0)
        shift["oof"][te] = s
        shift["pred"][te] = np.digitize(s, ref["thresholds"][k]) + 1
    summarise("train hi-res -> test 256 px", "spatial", lab, shift, ref)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "extract-w256", "eval", "w256"])
    ap.add_argument("--quick", action="store_true", help="spatial protocol only")
    ap.add_argument("--only", choices=["weights", "variants", "level1"], default=None)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--kinds", default=None,
                    help="comma list of spatial,loro,bp_bbox,cell3km")
    ap.add_argument("--names", default=None, help="comma list of variant names")
    ap.add_argument("--out", default=None, help="results JSON (default ml/cache/...)")
    args = ap.parse_args()
    {"extract": lambda: cmd_extract(), "extract-w256": lambda: cmd_extract_w256(),
     "eval": lambda: cmd_eval(args), "w256": lambda: cmd_w256(args)}[args.cmd]()


if __name__ == "__main__":
    main()
