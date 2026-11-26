#!/usr/bin/env python3
"""OSM `smoothness=` / `surface=` tags as free labels and context for the RQI model.

Offline: reads only the cached Overpass responses in data/osm/ (no network) and
the local DB read-only (headings of sv_* frames, today's new frames). Every frame
is snapped to the nearest OSM way within 20 m whose bearing fits the frame heading
(the segment builder's rule, backend map_matching.LineIndex).

Reports (numbers in ML severity numbering, 1 = Kiváló … 4 = Rossz):
  1. coverage of smoothness / surface tags on labelled and on new frames;
  2. agreement OSM smoothness vs human label (crosstab, Spearman, QWK);
  3. model error by surface type (does sett/cobblestone explain over-rating?);
  4. spatial-CV test: champion score + OSM one-hot -> ridge stack, paired
     against the champion (same harness as Era 9, ml/vlm_feature_eval.py).

Usage: PY ml/osm_tags.py [--skip-cv]
"""
import argparse
import glob
import json
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV
from sklearn.metrics import cohen_kappa_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rqi_scale as R  # noqa: E402
import spatial_cv as S  # noqa: E402

ROOT = S.ROOT
sys.path.insert(1, os.path.join(ROOT, "backend"))  # this checkout, not an installed copy
from app.services.map_matching import LineIndex  # noqa: E402

warnings.filterwarnings("ignore")
OSM_DIR = os.path.join(ROOT, "data", "osm")
OUT = os.path.join(ROOT, "ml", "cache", "osm_tags_frames.csv")

# OSM smoothness -> severity class (1 = Kiváló … 4 = Rossz; the model has no 5)
SMOOTH = {"excellent": 1, "good": 2, "intermediate": 3, "bad": 4,
          "very_bad": 4, "horrible": 4, "very_horrible": 4, "impassable": 4}
SURFACE_GROUP = {
    "asphalt": "asphalt", "concrete": "concrete", "concrete:plates": "concrete",
    "concrete:lanes": "concrete", "paving_stones": "paving_stones",
    "sett": "sett_cobble", "cobblestone": "sett_cobble",
    "unhewn_cobblestone": "sett_cobble",
}
UNPAVED = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "ground",
           "grass", "earth", "sand", "pebblestone", "mud"}


class Way:
    __slots__ = ("id", "coords", "tags")

    def __init__(self, el):
        self.id = el["id"]
        self.coords = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
        self.tags = el.get("tags") or {}


def load_ways():
    ways = {}
    for f in glob.glob(os.path.join(OSM_DIR, "*.json")):
        try:
            payload = json.load(open(f))
        except Exception:
            continue
        for el in payload.get("elements", []):
            if el.get("type") == "way" and "highway" in (el.get("tags") or {}):
                w = Way(el)
                if len(w.coords) >= 2:
                    ways[w.id] = w
    return ways


def surface_group(s):
    if not isinstance(s, str) or not s:
        return "missing"
    return SURFACE_GROUP.get(s, "unpaved" if s in UNPAVED else "other")


def _db():
    import sqlalchemy as sa
    from dotenv import dotenv_values
    url = dotenv_values(os.path.join(ROOT, ".env")).get("DATABASE_URL")
    eng = sa.create_engine(url)
    return sa, eng


def labelled_frames():
    """Champion OOF table (severity numbering) + heading per frame."""
    df = pd.read_csv(os.path.join(ROOT, "ml", "cache", "oof_spatial_champion.csv"))
    head = {}
    sv_ids = []
    for f in df.image_filename:
        m = re.match(r"sv_(\d+)_", f)
        if m:
            sv_ids.append(int(m.group(1)))
        else:
            h = re.search(r"_(-?\d+(?:\.\d+)?)\.jpg$", f)
            head[f] = float(h.group(1)) if h else None
    sa, eng = _db()
    with eng.connect() as c:
        c.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = c.execute(sa.text("SELECT id, heading FROM street_view_images WHERE id = ANY(:ids)"),
                         {"ids": sv_ids}).fetchall()
    by_id = {r.id: r.heading for r in rows}
    for f in df.image_filename:
        m = re.match(r"sv_(\d+)_", f)
        if m:
            head[f] = by_id.get(int(m.group(1)))
    df["heading"] = df.image_filename.map(head)
    return df


def new_frames(since="2026-11-26"):
    """Frames collected since `since` (today's Budapest collection), model score
    converted to severity; frame_quality unusable ones left out."""
    sa, eng = _db()
    with eng.connect() as c:
        c.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = c.execute(sa.text(
            "SELECT id, latitude AS lat, longitude AS lon, heading, "
            "(analysis_metadata->>'dino_score')::float AS score "
            "FROM street_view_images WHERE created_at >= :since "
            "AND COALESCE((analysis_metadata->'frame_quality'->>'usable')::boolean, true) "
            "AND analysis_metadata->>'dino_score' IS NOT NULL"), {"since": since}).fetchall()
    d = pd.DataFrame([dict(r._mapping) for r in rows])
    if len(d):
        d["score"] = d["score"].map(R.SCALE.to_severity)
    return d


def snap(df, index, ways):
    sm, sf, hw, wid = [], [], [], []
    for lat, lon, h in zip(df.lat, df.lon, df.heading):
        m = index.snap((lat, lon), None if pd.isna(h) else float(h))
        t = ways[m.line_id].tags if m else {}
        wid.append(m.line_id if m else None)
        sm.append(t.get("smoothness"))
        sf.append(t.get("surface"))
        hw.append(t.get("highway"))
    return df.assign(way_id=wid, smoothness=sm, surface=sf, highway=hw,
                     surface_group=[surface_group(s) for s in sf],
                     osm_class=[SMOOTH.get(s) for s in sm])


def coverage(name, d):
    n = len(d)
    snapped = d.way_id.notna().mean()
    print(f"  {name:28s} n={n:5d}  on a way {snapped:5.1%}  smoothness {d.smoothness.notna().mean():5.1%}"
          f"  surface {d.surface.notna().mean():5.1%}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-cv", action="store_true")
    args = ap.parse_args(argv)

    ways = load_ways()
    index = LineIndex(ways.values())
    n_sm = sum(1 for w in ways.values() if "smoothness" in w.tags)
    n_sf = sum(1 for w in ways.values() if "surface" in w.tags)
    print(f"OSM cache: {len(ways)} highway ways; smoothness on {n_sm} ({n_sm/len(ways):.1%}), "
          f"surface on {n_sf} ({n_sf/len(ways):.1%})\n")

    lab = snap(labelled_frames(), index, ways)
    new = new_frames()
    new = snap(new, index, ways) if len(new) else new
    lab.to_csv(OUT, index=False)

    print("1) Coverage")
    coverage("labelled (all)", lab)
    for a, g in lab.groupby("area"):
        coverage(f"labelled {a}", g)
    if len(new):
        coverage("new since 2026-11-26", new)

    print("\n2) Agreement: OSM smoothness vs human label (severity 1 = Kiváló … 4 = Rossz)")
    s = lab[lab.osm_class.notna()]
    if len(s):
        print(pd.crosstab(s.human_rqi, s.smoothness).to_string())
        rho = spearmanr(s.osm_class, s.human_rqi).correlation
        qwk = cohen_kappa_score(s.human_rqi, s.osm_class.astype(int), weights="quadratic",
                                labels=R.MODEL_LEVELS)
        exact = float((s.osm_class == s.human_rqi).mean())
        mq = cohen_kappa_score(s.human_rqi, s.pred_rqi, weights="quadratic", labels=R.MODEL_LEVELS)
        print(f"  n={len(s)} frames on {s.way_id.nunique()} ways: Spearman {rho:.2f}, QWK {qwk:.2f}, "
              f"exact {exact:.0%}   (model on the same frames: QWK {mq:.2f})")
        bad_h = s.human_rqi >= R.BAD_FROM
        bad_o = s.osm_class >= R.BAD_FROM
        print(f"  good/bad agreement {np.mean(bad_h == bad_o):.0%}; "
              f"OSM says bad on {bad_o.mean():.0%}, human {bad_h.mean():.0%}")
    else:
        print("  no labelled frame on a smoothness-tagged way")

    print("\n3) Model error by OSM surface (pred − human, + = model says worse)")
    t = lab.assign(err=lab.pred_rqi - lab.human_rqi, serr=lab.score - lab.human_rqi,
                   abs_err=(lab.pred_rqi - lab.human_rqi).abs())
    print(t.groupby("surface_group").agg(n=("err", "size"), class_bias=("err", "mean"),
                                         score_bias=("serr", "mean"), mae=("abs_err", "mean"))
          .round(2).sort_values("n", ascending=False).to_string())
    if len(new):
        print("  new frames: model score (severity) by surface")
        print(new.groupby("surface_group").score.agg(["size", "mean"]).round(2)
              .sort_values("size", ascending=False).to_string())

    if args.skip_cv:
        return 0

    print("\n4) Spatial CV: champion score + OSM features -> ridge stack (paired vs champion)")
    import vlm_feature_eval as V
    from vlm_attributes import champion_oof, dataset
    feats, df = dataset()
    o = df[["image_filename"]].merge(lab[["image_filename", "surface_group", "osm_class"]],
                                     on="image_filename", how="left")
    groups_s = ["asphalt", "concrete", "paving_stones", "sett_cobble", "unpaved", "other", "missing"]
    A = np.column_stack([(o.surface_group.fillna("missing") == g).astype(float) for g in groups_s]
                        + [o.osm_class.fillna(0).values, o.osm_class.isna().astype(float)])
    A = A[:, A.std(0) > 0]
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    groups = S.grid_cells(df.lat.values, df.lon.values)
    Xd = np.hstack([feats["cls"], feats["patch"]])
    ref = champion_oof(feats, df)
    V.ctx = V.Ctx(Xd, A, y, yc, groups)
    ridge = lambda: RidgeCV(alphas=np.logspace(-1, 3.5, 10))  # noqa: E731
    res = V.nested_generic(V.fp_stack("vlm", ridge), yc, groups)
    res_none = V.nested_generic(V.fp_stack("none", ridge), yc, groups)
    for name, r in (("champion", ref), ("champion score -> ridge (control)", res_none),
                    ("champion score + OSM -> ridge", res)):
        m = S.ordinal_metrics(yc, r["pred"], r["oof"])
        line = f"  {name:36s} QWK {m['qwk']:.3f}  MAE {m['mae']:.3f}  AUC {m['bad_auc']:.3f}"
        if r is not ref:
            d = S.paired_bootstrap_delta(yc, ref, r, groups)
            line += f"  ΔQWK {d['qwk'][0]:+.3f} [{d['qwk'][1]:+.3f}, {d['qwk'][2]:+.3f}]"
        print(line)
    bud = (df.area == "budapest").values
    for name, r in (("champion", ref), ("+ OSM", res)):
        m = S.ordinal_metrics(yc[bud], r["pred"][bud], r["oof"][bud])
        print(f"  Budapest {name:10s} QWK {m['qwk']:.3f}  AUC {m['bad_auc']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
