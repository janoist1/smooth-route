#!/usr/bin/env python3
"""
Era 17 (T-98): Era 9's VLM attributes used ONLY on motorway/trunk frames.

The largest single error of the champion (Era 16) is the sealed-crack
motorway: owner says Jó, the model says Kiváló. Era 9's stack (champion SVR
score + 15 VLM pavement attributes -> ridge) fixed exactly those frames, but
needs a VLM call per frame. Here the attributes are given to the stacker only
on frames whose OSM road class is motorway/trunk(_link) — a class the backend
already knows for every frame (segment snap, no VLM call) — so a rollout only
calls the VLM there. Everyone else gets zeros plus an indicator.

Variants (all paired against the champion on identical folds, via
ml/external_data.run_cv: official spatial 1 km, leave-one-area-out, Budapest
box held out; nested cut-points on our labels):
  champion             SVR-RBF on DINOv2-small cls+patch
  stack everywhere     Era 9 reference: [DINO | attributes] -> StackedVLMHead
  stack motorway only  [DINO | attributes * m | m], m = OSM motorway/trunk(_link)
  ... 6 defects        the same with only the six defect grades (fewer weights)
  motorway-only correction  champion score everywhere; on motorway rows a ridge on
                       [score, attributes] fitted on motorway rows only
  ..., champion cuts   the same scores cut with the champion's nested cut-points
plus metrics on the motorway subset (bias, exact, Jó -> Kiváló rate).

Subcommands
  highways  read-only DB pass: OSM highway class per frame with the label
            queue's heading-aware segment snap -> data/cache/frame_highways.csv
  eval      the experiment (data on disk only: ml/cache/vlm_attributes.csv)
  cost      rollout size: usable motorway/trunk frames and segments in the DB

Usage: /Users/i/Dev/smooth-route/.venv/bin/python ml/motorway_vlm.py highways|eval|cost
Result (2026-11-26): docs/MODEL_EXPERIMENTS.md "Era 17".
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import external_data as X  # noqa: E402
import rqi_scale as R  # noqa: E402
import spatial_cv as S  # noqa: E402

ROOT = S.ROOT
HIGHWAYS = os.path.join(ROOT, "data", "cache", "frame_highways.csv")  # gitignored
OUT_JSON = os.path.join(X.CACHE, "motorway_vlm_results.json")
MOTORWAY = ("motorway", "motorway_link", "trunk", "trunk_link")  # = weak_spots.json
DEFECTS = ("cracks_ord", "patches_ord", "potholes_ord", "ravelling_ord",
           "edge_damage_ord", "rutting_ord")
JO = int(R.SCALE.to_severity(R.SCALE.value_of("good")))
KIVALO = int(R.SCALE.to_severity(R.SCALE.value_of("excellent")))


def _backend():
    sys.path.insert(0, os.path.join(ROOT, "backend"))


def cmd_highways():
    """OSM class per frame, exactly as the label queue links frames to segments."""
    _backend()
    from sqlalchemy import text
    from app.core.database import SessionLocal
    from app.services import label_queue as lq
    from app.services.segment_read import highways_for_frames
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        rows = db.execute(text("""
            SELECT id, image_url, latitude, longitude, heading,
                   lower(trim(analysis_metadata::jsonb->'frame_quality'->>'usable')) AS usable
            FROM street_view_images WHERE latitude IS NOT NULL""")).all()
        hw = highways_for_frames(db, [lq.Frame(id=r.id, lat=r.latitude, lon=r.longitude,
                                               heading=r.heading) for r in rows])
    df = pd.DataFrame({"id": [r.id for r in rows],
                       "image_filename": [(r.image_url or "").replace("images/", "") for r in rows],
                       "usable": [r.usable != "false" for r in rows],
                       "highway": [hw.get(r.id) or "" for r in rows]})
    os.makedirs(os.path.dirname(HIGHWAYS), exist_ok=True)
    df.to_csv(HIGHWAYS, index=False)
    print(f"{len(df)} frames, {int((df.highway != '').sum())} linked -> {HIGHWAYS}")


def motorway_mask(files):
    h = pd.read_csv(HIGHWAYS).drop_duplicates("image_filename").set_index("image_filename")
    hw = h.reindex(list(files))["highway"].fillna("")
    return hw.isin(MOTORWAY).values, hw.values


def stack_head():
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from vlm_heads import StackedVLMHead
    return make_pipeline(StandardScaler(), StackedVLMHead(n_base=768))


class MotorwayCorrection:
    """Champion SVR everywhere; on motorway rows only, a ridge on [cross-fitted
    SVR score, attributes] fitted on the training motorway rows. Other frames
    keep the champion score exactly. X = [DINO (n_base) | attributes | m]."""

    def __init__(self, n_base=768, n_folds=5, min_rows=30):
        self.n_base, self.n_folds, self.min_rows = n_base, n_folds, min_rows

    def _split(self, X):
        X = np.asarray(X, dtype=float)
        return X[:, :self.n_base], X[:, self.n_base:-1], X[:, -1] > 0.5

    def fit(self, X, y):
        from sklearn.linear_model import RidgeCV
        from sklearn.model_selection import KFold
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVR
        Xb, A, m = self._split(X)
        y = np.asarray(y, dtype=float)
        self.sc_ = StandardScaler().fit(Xb)
        Z = self.sc_.transform(Xb)
        svr = lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)  # noqa: E731
        self.base_ = svr().fit(Z, y)
        self.ridge_ = None
        if m.sum() >= self.min_rows:  # no motorway labels -> no correction
            oof = np.zeros(len(y))
            for tr, te in KFold(self.n_folds, shuffle=False).split(Z):
                oof[te] = svr().fit(Z[tr], y[tr]).predict(Z[te])
            self.ridge_ = make_pipeline(StandardScaler(), RidgeCV(
                alphas=[0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000])).fit(
                np.column_stack([oof[m], A[m]]), y[m])
        return self

    def predict(self, X):
        Xb, A, m = self._split(X)
        s = self.base_.predict(self.sc_.transform(Xb))
        if self.ridge_ is not None and m.any():
            s[m] = self.ridge_.predict(np.column_stack([s[m], A[m]]))
        return s


def subset_metrics(lab, res, s):
    yc, p, sc = lab["yc"][s], res["pred"][s], res["oof"][s]
    jo = yc == JO
    m = S.ordinal_metrics(yc, p, sc)
    return {"n": int(s.sum()), "qwk": m["qwk"], "exact": m["exact"], "mae": m["mae"],
            "bias": float(sc.mean() - lab["y"][s].mean()),
            "jo_to_kivalo": float(np.mean(p[jo] == KIVALO)) if jo.any() else float("nan"),
            "n_jo": int(jo.sum())}


def cmd_eval(args):
    global OUT_JSON
    OUT_JSON = args.out or OUT_JSON
    from vlm_attributes import MODEL_COLUMNS, attribute_matrix
    lab = X.load_ours()
    mw, _ = motorway_mask(lab["files"])
    A = attribute_matrix(list(lab["files"]))
    print(f"labelled frames {len(mw)}, OSM motorway/trunk {int(mw.sum())} "
          f"({pd.Series(lab['area'][mw]).value_counts().to_dict()}); attributes {A.shape[1]}")
    Xd = lab["X"]
    D = A[:, [MODEL_COLUMNS.index(c) for c in DEFECTS]]
    plan = [("champion", {}),
            ("stack everywhere (Era 9)", {"X": np.hstack([Xd, A]), "make_head": stack_head}),
            ("stack motorway only", {"X": np.hstack([Xd, A * mw[:, None], mw[:, None]]),
                                     "make_head": stack_head}),
            # fewer weights to learn from one motorway stretch: defect grades only
            ("stack motorway only (6 defects)", {"X": np.hstack([Xd, D * mw[:, None], mw[:, None]]),
                                                "make_head": stack_head})]
    plan.append(("motorway-only correction", {"X": np.hstack([Xd, A, mw[:, None]]),
                                               "make_head": MotorwayCorrection}))
    # same scores, the champion's own (nested) cut-points: other frames unchanged
    plan.append(("motorway-only correction (champion cuts)",
                 {"X": np.hstack([Xd, A, mw[:, None]]), "make_head": MotorwayCorrection,
                  "recut": True}))
    if args.names:
        keep = set(args.names.split(",")) | {"champion"}
        plan = [(n, kw) for n, kw in plan if n in keep]
    rows, refs = [], {}
    for kind in args.kinds.split(","):
        for name, kw in plan:
            kw = dict(kw)
            recut = kw.pop("recut", False)
            res = X.run_cv(lab, kind, n_jobs=args.jobs, **kw)
            if recut:  # identical folds -> re-cut each fold with the champion's cut-points
                ch = refs[kind]
                for k, (_, te) in enumerate(X.make_folds(lab, kind)):
                    res["pred"][te] = np.digitize(res["oof"][te], ch["thresholds"][k]) + 1
                res["thresholds"] = ch["thresholds"]
            if name == "champion":
                refs[kind] = res
            ref = None if name == "champion" else refs[kind]
            row = X.summarise(name, kind, lab, res, ref)
            te = np.zeros(len(mw), bool)
            te[res["test"]] = True
            for tag, s in (("mw", te & mw), ("other", te & ~mw)):
                if s.sum() < 20:
                    continue
                row[tag] = subset_metrics(lab, res, s)
                if ref is not None and len(np.unique(lab["groups"][s])) > 1:
                    d = S.paired_bootstrap_delta(lab["yc"][s], X._sub(ref, s), X._sub(res, s),
                                                 lab["groups"][s])
                    row[tag]["d_qwk"] = d["qwk"]
                sm = row[tag]
                dq = (f" Δ{sm['d_qwk'][0]:+.3f} [{sm['d_qwk'][1]:+.3f},{sm['d_qwk'][2]:+.3f}]"
                      if "d_qwk" in sm else "")
                print(f"          {tag:5s} n={sm['n']:4d} QWK {sm['qwk']:.3f} exact "
                      f"{sm['exact']:.3f} bias {sm['bias']:+.2f} Jó→Kiváló "
                      f"{sm['jo_to_kivalo']:.0%} of {sm['n_jo']}{dq}", flush=True)
            rows.append(row)
            json.dump({"rows": rows}, open(OUT_JSON, "w"), default=X._json, indent=1)
    print(f"saved {OUT_JSON}")


def cmd_cost():
    """How many VLM calls would a motorway-only rollout need?"""
    _backend()
    from sqlalchemy import text
    from app.core.database import SessionLocal
    h = pd.read_csv(HIGHWAYS)
    h = h[h["usable"]]
    mw = h["highway"].isin(MOTORWAY)
    labelled = set(pd.read_csv(os.path.join(X.CACHE, "dataset_v2.csv"))["image_filename"])
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        # dino_rqi_score = the live model's class on the canonical scale (DB side)
        cls = pd.read_sql(text("SELECT id, dino_rqi_score AS c FROM street_view_images"),
                          db.connection()).set_index("id")["c"]
        seg = db.execute(text("""SELECT count(*), coalesce(sum(length_m), 0) FROM road_segments
                                 WHERE n_images > 0 AND highway = ANY(:hw)"""),
                         {"hw": list(MOTORWAY)}).first()
    kiv = mw.values & (cls.reindex(h["id"]).values == R.SCALE.value_of("excellent"))
    out = {"usable_frames": int(len(h)), "motorway_trunk_frames": int(mw.sum()),
           "motorway_trunk_unlabelled": int((mw & ~h["image_filename"].isin(labelled)).sum()),
           "motorway_trunk_predicted_kivalo": int(kiv.sum()),
           "motorway_trunk_segments": int(seg[0]), "motorway_trunk_km": float(seg[1]) / 1000,
           "by_class": h[mw]["highway"].value_counts().to_dict()}
    print(json.dumps(out, indent=1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["highways", "eval", "cost"])
    ap.add_argument("--kinds", default="spatial,loro,bp_bbox")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--names", default=None, help="comma list of variant names")
    ap.add_argument("--out", default=None, help="results JSON")
    args = ap.parse_args()
    {"highways": cmd_highways, "eval": lambda: cmd_eval(args), "cost": cmd_cost}[args.cmd]()


if __name__ == "__main__":
    main()
