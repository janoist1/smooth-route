#!/usr/bin/env python3
"""
Era 9 — do VLM attributes make the RQI model more reliable?

Evaluates the merged VLM attributes (ml/cache/vlm_attributes.csv, built by
ml/vlm_attributes.py) on the OFFICIAL spatial protocol (ml/spatial_cv.py:
1 km cells, StratifiedGroupKFold 5, seed 42, nested cut-points) and compares
every candidate PAIRED against the champion recipe (DINOv2-small cls+patch +
SVR C=1) with the cell bootstrap of the difference.

Candidates
  (0)  VLM rqi_guess used directly as the label (no model)
  (a)  attributes alone -> small model (Ridge / SVR / ordinal logit / HistGB)
  (b)  champion DINO features + attributes -> SVR (attribute block re-weighted)
  (c)  champion score + attributes, stacked (champion score is inner-OOF on the
       training fold, so the stacker never sees an in-sample score)
  (d)  convex blend of the champion score with rqi_guess (alpha fit on train)
  (D*) DISTILLED variants of the above: ridge heads on DINO features predict
       the attributes (trained on the training fold's VLM attributes only); the
       PREDICTED attributes replace the VLM ones -> no VLM call at inference.

Also: Budapest-only and per-class recall, champion errors by attribute value,
distillation fidelity, shifted-grid robustness of promising candidates, and
the label-audit list (data/vlm/label_audit.csv).

Usage:  python ml/vlm_feature_eval.py [--audit-only]
        python ml/vlm_feature_eval.py --shift '<candidate name>' --grid K
"""
import argparse
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import cohen_kappa_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from heads import OrdinalLogistic  # noqa: E402
from vlm_attributes import (MERGED, SCHEMA,  # noqa: E402
                            champion_oof, dataset, encode)

warnings.filterwarnings("ignore")
ROOT = S.ROOT
CACHE = os.path.join(ROOT, "ml", "cache")
AUDIT = os.path.join(ROOT, "data", "vlm", "label_audit.csv")
SUMMARY = os.path.join(CACHE, "vlm_eval_summary.json")
RARE = 0.01  # drop one-hot columns rarer than 1 % (unsupervised, label-free)


def champ_head():
    return SVR(C=1.0, gamma="scale", epsilon=0.05)


class BlockWeight(BaseEstimator, TransformerMixin):
    """Multiply columns [start:] by w (applied after StandardScaler)."""

    def __init__(self, start=0, w=1.0):
        self.start = start
        self.w = w

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = np.array(X, dtype=float, copy=True)
        X[:, self.start:] *= self.w
        return X


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load_all(path=MERGED):
    feats, df = dataset()
    att = pd.read_csv(path)
    att = df[["image_filename"]].merge(att, on="image_filename", how="left")
    miss = att["rqi_guess"].isna()
    if miss.any():  # impute with the mode so every frame stays in the CV
        for k in list(SCHEMA) + ["obstruction_pct", "rqi_guess"]:
            att.loc[miss, k] = att.loc[~miss, k].mode().iloc[0]
    A, names = encode(att)
    keep = [i for i, n in enumerate(names)
            if A[:, i].std() > 0 and ("=" not in n or A[:, i].mean() >= RARE)]
    A, names = A[:, keep], [names[i] for i in keep]
    return feats, df, att, A, names, int(miss.sum())


# --------------------------------------------------------------------------
# generic nested spatial CV for arbitrary fit-predict functions
# --------------------------------------------------------------------------
def nested_generic(fp, yc, groups, seed=S.SEED):
    """Same protocol as S.nested_spatial_cv, for fp(tr_idx, te_idx)->score."""
    folds = S.spatial_folds(yc, groups, S.N_SPLITS, seed)
    oof = np.zeros(len(yc))
    pred = np.zeros(len(yc), dtype=int)
    fold = np.zeros(len(yc), dtype=int)
    for k, (tr, te) in enumerate(folds):
        oof[te] = fp(tr, te)
        fold[te] = k
        ioof = np.zeros(len(tr))
        for itr, ite in S.spatial_folds(yc[tr], groups[tr], S.INNER_SPLITS,
                                        seed):
            ioof[ite] = fp(tr[itr], tr[ite])
        pred[te] = np.digitize(oof[te], S.tune_thresholds(yc[tr], ioof)) + 1
    return {"oof": oof, "pred": pred, "fold": fold}


class Ctx:
    """Holds data + memoised champion scores / distilled attributes."""

    def __init__(self, Xd, A, y, yc, groups):
        self.Xd, self.A, self.y, self.yc, self.g = Xd, A, y, yc, groups
        self._champ, self._dist = {}, {}

    @staticmethod
    def _key(tr, te):
        return (hash(tr.tobytes()), hash(te.tobytes()))

    def _inner(self, tr):
        return S.spatial_folds(self.yc[tr], self.g[tr], S.INNER_SPLITS, S.SEED)

    def champ_scores(self, tr, te):
        """(inner-OOF champion score on tr, champion(tr) score on te)."""
        k = self._key(tr, te)
        if k not in self._champ:
            s_tr = np.zeros(len(tr))
            for itr, ite in self._inner(tr):
                s_tr[ite] = S._fit_predict(champ_head, self.Xd[tr][itr],
                                           self.y[tr][itr], self.Xd[tr][ite])
            s_te = S._fit_predict(champ_head, self.Xd[tr], self.y[tr],
                                  self.Xd[te])
            self._champ[k] = (s_tr, s_te)
        return self._champ[k]

    def distilled(self, tr, te, target="att"):
        """Attributes predicted from DINO by ridge heads trained on tr's VLM
        attributes: (inner-OOF prediction on tr, prediction on te).
        target="y" is the CONTROL: the same ridge channel distilled from the
        human label instead of the VLM — any gain it shares is not VLM info."""
        k = self._key(tr, te) + (target,)
        T = self.A if target == "att" else self.y[:, None]
        if k not in self._dist:
            def fit_pred(a, b):
                m = make_pipeline(StandardScaler(), RidgeCV(
                    alphas=np.logspace(0, 4.5, 10), alpha_per_target=True))
                m.fit(self.Xd[a], T[a])
                return m.predict(self.Xd[b]).reshape(len(b), -1)
            a_tr = np.zeros((len(tr), T.shape[1]))
            for itr, ite in self._inner(tr):
                a_tr[ite] = fit_pred(tr[itr], tr[ite])
            self._dist[k] = (a_tr, fit_pred(tr, te))
        return self._dist[k]


def fp_features(X, make_model):
    def fp(tr, te):
        return S._fit_predict(make_model, X[tr], ctx.y[tr], X[te])
    return fp


def fp_dino_plus(att_source, w, make_head=champ_head):
    """[DINO | w * attributes] -> head; att_source 'vlm' or 'distilled'."""
    d = ctx.Xd.shape[1]

    def fp(tr, te):
        if att_source == "vlm":
            a_tr, a_te = ctx.A[tr], ctx.A[te]
        elif att_source == "control":
            a_tr, a_te = ctx.distilled(tr, te, target="y")
        else:
            a_tr, a_te = ctx.distilled(tr, te)
        Xtr = np.hstack([ctx.Xd[tr], a_tr])
        Xte = np.hstack([ctx.Xd[te], a_te])
        return S._fit_predict(
            lambda: make_pipeline(BlockWeight(d, w), make_head()),
            Xtr, ctx.y[tr], Xte)
    return fp


def fp_attrs_only_distilled(make_model):
    def fp(tr, te):
        a_tr, a_te = ctx.distilled(tr, te)
        return S._fit_predict(make_model, a_tr, ctx.y[tr], a_te)
    return fp


def fp_stack(att_source, make_stacker):
    def fp(tr, te):
        s_tr, s_te = ctx.champ_scores(tr, te)
        if att_source == "vlm":
            a_tr, a_te = ctx.A[tr], ctx.A[te]
        elif att_source == "none":
            a_tr, a_te = np.zeros((len(tr), 0)), np.zeros((len(te), 0))
        elif att_source == "control":
            a_tr, a_te = ctx.distilled(tr, te, target="y")
        else:
            a_tr, a_te = ctx.distilled(tr, te)
        return S._fit_predict(make_stacker, np.column_stack([s_tr, a_tr]),
                              ctx.y[tr], np.column_stack([s_te, a_te]))
    return fp


def fp_blend(guess_col):
    """(1-a)*champion + a*rqi_guess, a in [0,1] fit by MSE on the train fold."""
    def fp(tr, te):
        s_tr, s_te = ctx.champ_scores(tr, te)
        if guess_col == "vlm":
            g_tr, g_te = ctx.guess[tr], ctx.guess[te]
        else:
            a_tr, a_te = ctx.distilled(tr, te)
            g_tr, g_te = a_tr[:, ctx.gi], a_te[:, ctx.gi]
        grid = np.linspace(0, 1, 21)
        mse = [np.mean(((1 - a) * s_tr + a * g_tr - ctx.y[tr]) ** 2)
               for a in grid]
        a = grid[int(np.argmin(mse))]
        ctx.alphas.append(float(a))
        return (1 - a) * s_te + a * g_te
    return fp


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def summarise(name, res, ref, yc, groups, bud):
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    d = S.paired_bootstrap_delta(yc, ref, res, groups)
    mb = S.ordinal_metrics(yc[bud], res["pred"][bud], res["oof"][bud])
    cm = confusion_matrix(yc, res["pred"], labels=[1, 2, 3, 4])
    rec = (cm.diagonal() / cm.sum(1)).round(3).tolist()
    row = {"name": name, **{k: round(m[k], 4) for k in
                            ("qwk", "mae", "exact", "bad_auc")},
           "d_qwk": [round(v, 4) for v in d["qwk"]],
           "d_mae": [round(v, 4) for v in d["mae"]],
           "d_auc": [round(v, 4) for v in d["bad_auc"]],
           "better": bool(d["qwk"][1] > 0),
           "bud_qwk": round(mb["qwk"], 4), "bud_mae": round(mb["mae"], 4),
           "bud_auc": round(mb["bad_auc"], 4), "recall": rec}
    print(f"{name:44s} QWK {m['qwk']:.3f} MAE {m['mae']:.3f} "
          f"AUC {m['bad_auc']:.3f} | ΔQWK {d['qwk'][0]:+.3f} "
          f"[{d['qwk'][1]:+.3f},{d['qwk'][2]:+.3f}] ΔMAE {d['mae'][0]:+.3f} "
          f"ΔAUC {d['bad_auc'][0]:+.3f} {'YES' if row['better'] else 'no ':3s}"
          f" | BUD QWK {mb['qwk']:.3f} AUC {mb['bad_auc']:.3f} | rec {rec}",
          flush=True)
    return row


def error_table(att, yc, ref):
    """Champion OOF error by attribute value."""
    err = ref["pred"] - yc
    out = {}
    print("\nChampion OOF error by VLM attribute value "
          "(n, MAE, bias = pred - true, mean human RQI)")
    for k in ["surface", "road_type", "lighting", "cracks", "patches",
              "potholes", "ravelling", "wet", "road_visible", "markings",
              "confidence"]:
        print(f"  {k}")
        for v, idx in att.groupby(k).groups.items():
            idx = np.asarray(list(idx))
            if len(idx) < 8:
                continue
            r = (len(idx), float(np.mean(np.abs(err[idx]))),
                 float(np.mean(err[idx])), float(np.mean(yc[idx])))
            out[f"{k}={v}"] = r
            print(f"    {str(v):22s} n={r[0]:4d} MAE {r[1]:.3f} "
                  f"bias {r[2]:+.3f} human {r[3]:.2f}")
    mw = (att.road_type == "motorway").values
    cr = (att.cracks != "none").values
    for nm, s in (("motorway & cracks", mw & cr), ("motorway & no cracks",
                                                   mw & ~cr)):
        if s.sum():
            print(f"  {nm:24s} n={s.sum():4d} MAE "
                  f"{np.mean(np.abs(err[s])):.3f} bias {np.mean(err[s]):+.3f}")
            out[nm] = (int(s.sum()), float(np.mean(np.abs(err[s]))),
                       float(np.mean(err[s])), float(np.mean(yc[s])))
    return out


def identical_pairs(df, thr=0.9995, max_m=40.0):
    """Pairs of frames that are the same picture (Street View returned the same
    panorama for two points ~10 m apart): grey 24x16 thumbnails correlate
    >= thr and the points are < max_m apart."""
    from PIL import Image

    def th(f):
        im = Image.open(os.path.join(ROOT, "data", "images", f))
        return np.asarray(im.convert("L").resize((24, 16)), float).ravel()
    T = np.stack([th(f) for f in df.image_filename])
    T = (T - T.mean(1, keepdims=True)) / (T.std(1, keepdims=True) + 1e-6)
    C = T @ T.T / T.shape[1]
    i, j = np.where(np.triu(C >= thr, 1))
    lat, lon = np.radians(df.lat.values), np.radians(df.lon.values)
    d = 6371000 * np.hypot((lon[i] - lon[j]) * np.cos(lat[i]), lat[i] - lat[j])
    keep = d < max_m
    return i[keep], j[keep]


def label_audit(df, att, ref, top=60):
    h = df["rqi"].values.astype(int)
    v = att["rqi_guess"].values.astype(int)
    m = ref["pred"]
    s = ref["oof"]
    conf = att["confidence"].values
    a = (np.abs(h - v) >= 2) & (np.abs(h - m) >= 2)
    b = (np.abs(h - v) >= 1) & (conf == "high") & (m == v)
    pi, pj = identical_pairs(df)
    twin = {}
    for x, z in zip(pi, pj):
        if h[x] != h[z]:
            twin.setdefault(x, z)
            twin.setdefault(z, x)
    c = np.zeros(len(h), bool)
    c[list(twin)] = True
    # tier d (fills the list up to `top`): VLM and model agree with each other
    # (medium confidence) and both disagree with the human
    dd = (v == m) & (h != m) & (conf == "medium") & ~(a | b | c)
    sel = a | b | c | dd
    pri = (np.abs(h - v) + np.abs(h - s) + 0.5 * (conf == "high")
           + 1.0 * a + 0.5 * c)
    rows = []
    for i in np.flatnonzero(sel):
        why = []
        if a[i]:
            why.append("VLM and model both >=2 off")
        elif b[i]:
            why.append("VLM (high conf) and model agree, human differs")
        elif dd[i]:
            why.append("VLM (medium conf) and model agree, human differs")
        if c[i]:
            k = twin[i]
            why.append(f"same picture as {df.image_filename.iloc[k]} "
                       f"labelled {h[k]}")
        rows.append({"image_filename": df.image_filename.iloc[i],
                     "human": int(h[i]), "model": int(m[i]),
                     "model_score": round(float(s[i]), 2), "vlm": int(v[i]),
                     "vlm_confidence": conf[i],
                     "area": df.area.iloc[i], "priority": round(float(pri[i]), 2),
                     "reason": "; ".join(why) + f"; VLM: {att.notes.iloc[i]}"})
    out = pd.DataFrame(rows)
    out["tier"] = ["d" if dd[i] else "abc" for i in np.flatnonzero(sel)]
    out = out.sort_values("priority", ascending=False)
    # every tier a/b/c frame is listed; tier d fills up to `top`
    core = out[out.tier == "abc"]
    fill = out[out.tier == "d"].head(max(0, top - len(core)))
    final = pd.concat([core, fill]).sort_values("priority", ascending=False)
    final = final.drop(columns="tier")
    print(f"\nLabel audit: {int(a.sum())} frames >=2 off from both, "
          f"{int(b.sum())} high-conf VLM==model!=human, {len(pi)} identical "
          f"pairs ({int(c.sum())} frames in pairs with conflicting labels), "
          f"{int(dd.sum())} medium-conf VLM==model!=human; "
          f"{len(out)} candidates, writing {len(final)}")
    final.to_csv(AUDIT, index=False)
    print(final.groupby(["human", "vlm"]).size().to_string())
    return {"both_off2": int(a.sum()), "vlm_model_agree": int(b.sum()),
            "identical_pairs": int(len(pi)),
            "identical_conflict_frames": int(c.sum()),
            "vlm_model_agree_medium": int(dd.sum()),
            "candidates": int(len(out)), "written": int(len(final))}


def shifted_grid(name, k, df, yc):
    """ΔQWK of one candidate vs the champion on shifted 1 km grid #k
    (offsets from a fixed RNG; run several k in parallel processes)."""
    rng = np.random.default_rng(7)
    offs = [tuple(rng.uniform(0, 1, 2)) for _ in range(k + 1)]
    off = offs[k]
    g = S.grid_cells(df.lat.values, df.lon.values, offset=off)
    ref = S.nested_spatial_cv(ctx.Xd, ctx.y, yc, g, champ_head)
    ctx.g = g
    ctx._champ, ctx._dist = {}, {}
    res = _makers(yc)[name](g)
    d = S.paired_bootstrap_delta(yc, ref, res, g, n_boot=500)
    out = {"name": name, "grid": k, "offset": [round(o, 3) for o in off],
           "d_qwk": [round(x, 4) for x in d["qwk"]],
           "d_mae": [round(x, 4) for x in d["mae"]],
           "d_auc": [round(x, 4) for x in d["bad_auc"]]}
    print(json.dumps(out), flush=True)
    return out


def main():
    global ctx
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--attrs", default=MERGED, help="merged attribute CSV")
    ap.add_argument("--out-dir", default="",
                    help="write audit/summary here instead (smoke tests)")
    ap.add_argument("--shift", default="",
                    help="only run this candidate on shifted grid --grid")
    ap.add_argument("--grid", type=int, default=0)
    args = ap.parse_args()
    global AUDIT, SUMMARY
    if args.out_dir:
        AUDIT = os.path.join(args.out_dir, "label_audit.csv")
        SUMMARY = os.path.join(args.out_dir, "vlm_eval_summary.json")

    feats, df, att, A, names, n_imp = load_all(args.attrs)
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    groups = S.grid_cells(df.lat.values, df.lon.values)
    bud = (df.area == "budapest").values
    Xd = np.hstack([feats["cls"], feats["patch"]])
    ref = champion_oof(feats, df)
    ctx = Ctx(Xd, A, y, yc, groups)
    ctx.guess = att["rqi_guess"].values.astype(float)
    ctx.gi = names.index("rqi_guess")
    ctx.alphas = []
    print(f"{len(df)} frames, {n_imp} imputed, {A.shape[1]} attribute columns, "
          f"{len(np.unique(groups))} cells\n")

    if args.shift:
        out = shifted_grid(args.shift, args.grid, df, yc)
        slug = "".join(ch if ch.isalnum() else "_" for ch in args.shift)
        with open(os.path.join(CACHE, f"vlm_shift_{slug}_{args.grid}.json"),
                  "w") as fh:
            json.dump(out, fh)
        return

    summary = {"n": len(df), "n_imputed": n_imp, "attr_cols": names}
    summary["audit"] = label_audit(df, att, ref)
    if args.audit_only:
        if os.path.exists(SUMMARY):
            old = json.load(open(SUMMARY))
            old["audit"] = summary["audit"]
            with open(SUMMARY, "w") as fh:
                json.dump(old, fh, indent=1, default=str)
        return
    summary["errors"] = error_table(att, yc, ref)

    rows = []
    t0 = time.time()
    print("\nPaired vs champion (official spatial CV, 95% cell-bootstrap CI)")
    rows.append(summarise("champion: DINO cls+patch + SVR", ref, ref, yc,
                          groups, bud))
    g = ctx.guess.astype(int)
    rows.append(summarise("(0) VLM rqi_guess as label",
                          {"oof": ctx.guess, "pred": g}, ref, yc, groups, bud))
    for conf in ("high", "medium", "low"):
        s = (att.confidence == conf).values
        if s.sum() > 20:
            print(f"    rqi_guess conf={conf:6s} n={s.sum():4d} QWK "
                  f"{cohen_kappa_score(yc[s], g[s], weights='quadratic'):.3f}"
                  f" exact {np.mean(yc[s] == g[s]):.2f} | champion QWK "
                  f"{cohen_kappa_score(yc[s], ref['pred'][s], weights='quadratic'):.3f}")

    no_guess = [i for i, n in enumerate(names) if n != "rqi_guess"]
    heads_a = {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-1, 3.5, 10)),
        "svr C=1": champ_head,
        "ordlogit": lambda: OrdinalLogistic(alpha=10.0),
        "histgb": _histgb,
    }
    for hn, hf in heads_a.items():
        rows.append(summarise(f"(a) attributes -> {hn}", S.nested_spatial_cv(
            A, y, yc, groups, hf), ref, yc, groups, bud))
    rows.append(summarise("(a) attributes w/o rqi_guess -> ridge",
                          S.nested_spatial_cv(A[:, no_guess], y, yc, groups,
                                              heads_a["ridge"]),
                          ref, yc, groups, bud))
    w_eq = float(np.sqrt(Xd.shape[1] / A.shape[1]))
    for w in (1.0, w_eq):
        rows.append(summarise(f"(b) DINO + attrs (w={w:.1f}) -> SVR",
                              nested_generic(fp_dino_plus("vlm", w), yc,
                                             groups), ref, yc, groups, bud))
    rows.append(summarise("(b) DINO + attrs -> ordlogit", S.nested_spatial_cv(
        np.hstack([Xd, A]), y, yc, groups, lambda: OrdinalLogistic(alpha=300.0)),
        ref, yc, groups, bud))
    stackers = {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-1, 3.5, 10)),
        "histgb": heads_a["histgb"],
    }
    rows.append(summarise("(c0) champion score restacked alone (ridge)",
                          nested_generic(fp_stack("none", stackers["ridge"]),
                                         yc, groups), ref, yc, groups, bud))
    for sn, sf in stackers.items():
        rows.append(summarise(f"(c) champion score + attrs -> {sn}",
                              nested_generic(fp_stack("vlm", sf), yc, groups),
                              ref, yc, groups, bud))
    ctx.alphas = []
    rows.append(summarise("(d) blend champion + rqi_guess",
                          nested_generic(fp_blend("vlm"), yc, groups),
                          ref, yc, groups, bud))
    summary["blend_alpha"] = [float(np.mean(ctx.alphas)),
                              float(np.min(ctx.alphas)),
                              float(np.max(ctx.alphas))]
    print(f"    blend alpha (mean/min/max over fits): {summary['blend_alpha']}")
    print(f"  [{time.time() - t0:.0f} s]\n\nDISTILLED (attributes predicted "
          f"from DINO, no VLM at inference)")
    rows.append(summarise("(Da) distilled attrs -> ridge",
                          nested_generic(fp_attrs_only_distilled(
                              heads_a["ridge"]), yc, groups),
                          ref, yc, groups, bud))
    for w in (1.0, w_eq):
        rows.append(summarise(f"(Db) DINO + distilled (w={w:.1f}) -> SVR",
                              nested_generic(fp_dino_plus("distilled", w), yc,
                                             groups), ref, yc, groups, bud))
    for sn, sf in stackers.items():
        rows.append(summarise(f"(Dc) champion + distilled -> {sn}",
                              nested_generic(fp_stack("distilled", sf), yc,
                                             groups), ref, yc, groups, bud))
    rows.append(summarise("(ctl) DINO + ridge-distilled HUMAN label -> SVR",
                          nested_generic(fp_dino_plus("control", 1.0), yc,
                                         groups), ref, yc, groups, bud))
    rows.append(summarise("(ctl) champion + ridge-distilled HUMAN -> ridge",
                          nested_generic(fp_stack("control",
                                                  stackers["ridge"]), yc,
                                         groups), ref, yc, groups, bud))
    ctx.alphas = []
    rows.append(summarise("(Dd) blend champion + distilled guess",
                          nested_generic(fp_blend("distilled"), yc, groups),
                          ref, yc, groups, bud))
    print(f"  [{time.time() - t0:.0f} s]")
    summary["rows"] = rows

    # distillation fidelity: how well DINO predicts each attribute (outer OOF)
    fid = {}
    folds = S.spatial_folds(yc, groups)
    Ahat = np.zeros_like(A)
    for tr, te in folds:
        Ahat[te] = ctx.distilled(tr, te)[1]
    print("\nDistillation fidelity (outer spatial OOF; r = Pearson)")
    for i, n in enumerate(names):
        r = float(np.corrcoef(A[:, i], Ahat[:, i])[0, 1])
        fid[n] = round(r, 3)
    print("  " + ", ".join(f"{n} {r:.2f}" for n, r in
                           sorted(fid.items(), key=lambda t: -t[1])))
    summary["fidelity"] = fid

    with open(SUMMARY, "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(f"\nsummary -> {os.path.relpath(SUMMARY, ROOT)}")


def _makers(yc):
    """name -> function(groups) re-running that candidate on other folds."""
    heads_a = {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-1, 3.5, 10)),
        "svr C=1": champ_head,
        "ordlogit": lambda: OrdinalLogistic(alpha=10.0),
        "histgb": _histgb,
    }
    stackers = {"ridge": heads_a["ridge"], "histgb": _histgb}
    w_eq = float(np.sqrt(ctx.Xd.shape[1] / ctx.A.shape[1]))
    m = {}
    m["(b) DINO + attrs -> ordlogit"] = (
        lambda g: S.nested_spatial_cv(np.hstack([ctx.Xd, ctx.A]), ctx.y, yc, g,
                                      lambda: OrdinalLogistic(alpha=300.0)))
    m["(ctl) DINO + ridge-distilled HUMAN label -> SVR"] = (
        lambda g: nested_generic(fp_dino_plus("control", 1.0), yc, g))
    for hn, hf in heads_a.items():
        m[f"(a) attributes -> {hn}"] = (
            lambda g, hf=hf: S.nested_spatial_cv(ctx.A, ctx.y, yc, g, hf))
    for w in (1.0, w_eq):
        m[f"(b) DINO + attrs (w={w:.1f}) -> SVR"] = (
            lambda g, w=w: nested_generic(fp_dino_plus("vlm", w), yc, g))
        m[f"(Db) DINO + distilled (w={w:.1f}) -> SVR"] = (
            lambda g, w=w: nested_generic(fp_dino_plus("distilled", w), yc, g))
    for sn, sf in stackers.items():
        m[f"(c) champion score + attrs -> {sn}"] = (
            lambda g, sf=sf: nested_generic(fp_stack("vlm", sf), yc, g))
        m[f"(Dc) champion + distilled -> {sn}"] = (
            lambda g, sf=sf: nested_generic(fp_stack("distilled", sf), yc, g))
    m["(d) blend champion + rqi_guess"] = (
        lambda g: nested_generic(fp_blend("vlm"), yc, g))
    m["(Dd) blend champion + distilled guess"] = (
        lambda g: nested_generic(fp_blend("distilled"), yc, g))
    return m


def _histgb():
    return HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.05, max_depth=3, l2_regularization=1.0,
        random_state=S.SEED)


ctx = None

if __name__ == "__main__":
    main()
