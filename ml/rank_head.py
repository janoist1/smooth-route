#!/usr/bin/env python3
"""
Era 13: does a pairwise RANKING term from VLM pair judgments improve the head?

Model (same features as the champion: DINOv2-small cls+patch, standardised):
    score(x) = phi(x) . w + b,    phi = Nystroem RBF map (gamma = 1/d, the SVR's
                                  gamma='scale' on standardised features)
    loss = mean_i (y_i - score(x_i))^2                          human labels
         + lam * mean_k softplus(-K * s_k * (score(a_k) - score(b_k)))   VLM pairs
         + alpha * |w|^2
with s_k = +1 if the VLM says frame a is the WORSE road, -1 if b is.
lam = 0 is plain kernel ridge (the pair-free control); lam is chosen NESTED
(inner spatial CV on the training labels, best inner QWK).

Evaluation uses HUMAN LABELS ONLY, under the official spatial protocol
(ml/spatial_cv.py) and leave-one-area-out (LORO), paired against the champion
SVR and against lam = 0 on identical folds (cell bootstrap). A pair is dropped
from a fold when either frame lies in a test cell (spatial) / the test area
(LORO). Cut-points: nested on inner spatial OOF, as the gate.

Pairs file (CSV): file_a, file_b (image filenames) or id_a, id_b (frame ids),
and vlm_pair in {A, B, equal} (A = frame a is worse); optional vlm_conf
(low/medium/high). "equal" rows are skipped. QA's format (worse_id,
better_id, worse_file, better_file, confidence) is accepted as well.

Usage:
  PY=/Users/i/Dev/smooth-route/.venv/bin/python
  $PY ml/rank_head.py data/vlm/pairwise/run1/scored.csv          # pilot sanity check
  $PY ml/rank_head.py data/vlm/pairwise/unsure_pairs.csv [--min-conf medium]
  ... --svr-base     # champion SVR + a pair-shaped ridge correction instead of kernel ridge
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.kernel_approximation import Nystroem
from sklearn.metrics import recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from semisup_regional import cell_keys, load  # noqa: E402

warnings.filterwarnings("ignore")
CACHE = os.path.join(S.ROOT, "ml", "cache")
LAMS = [0.0, 0.3, 1.0, 3.0]
ALPHA = 1e-3
K = 4.0            # pair-loss sharpness: a gap of ~0.5 class costs little
N_COMP = 600
CONF_RANK = {"low": 0, "medium": 1, "high": 2}


# --------------------------------------------------------------------------
class RankRidge:
    """Kernel ridge (Nystroem) + pairwise logistic term, fitted with L-BFGS."""

    def __init__(self, lam, alpha=ALPHA, seed=S.SEED, svr_base=False):
        self.lam, self.alpha, self.seed, self.svr_base = lam, alpha, seed, svr_base

    def _base(self, X):
        return self.base.predict(X) if self.svr_base else np.zeros(len(X))

    def fit(self, X, y, Pa=None, Pb=None, s=None):
        if self.svr_base:   # champion SVR + a ridge CORRECTION shaped by the pairs
            self.base = make_pipeline(StandardScaler(),
                                      SVR(C=1.0, gamma="scale", epsilon=0.05)).fit(X, y)
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        fit_on = Z if Pa is None else np.vstack([Z, self.sc.transform(Pa),
                                                 self.sc.transform(Pb)])
        self.ny = Nystroem(kernel="rbf", gamma=1.0 / X.shape[1],
                           n_components=min(N_COMP, len(fit_on)),
                           random_state=self.seed).fit(fit_on)
        F = self.ny.transform(Z)
        use_pairs = self.lam > 0 and Pa is not None and len(Pa)
        o = self._base(X)
        if use_pairs:
            D = self.ny.transform(self.sc.transform(Pa)) - self.ny.transform(self.sc.transform(Pb))
            od = self._base(Pa) - self._base(Pb)
        n, d = F.shape
        ym = 0.0 if self.svr_base else y.mean()

        def obj(p):
            w, b = p[:d], p[d]
            r = F @ w + b + o - y
            f = (r @ r) / n + self.alpha * (w @ w)
            g_w = 2 * F.T @ r / n + 2 * self.alpha * w
            g_b = 2 * r.sum() / n
            if use_pairs:
                m = -K * s * (od + D @ w)
                f += self.lam * np.mean(np.logaddexp(0, m))
                sig = 1 / (1 + np.exp(-m))
                g_w += self.lam * (D.T @ (sig * -K * s)) / len(s)
            return f, np.r_[g_w, g_b]

        p0 = np.r_[np.zeros(d), ym]
        res = minimize(obj, p0, jac=True, method="L-BFGS-B",
                       options={"maxiter": 500})
        self.w, self.b = res.x[:d], res.x[d]
        return self

    def predict(self, X):
        return self.ny.transform(self.sc.transform(X)) @ self.w + self.b + self._base(X)


# --------------------------------------------------------------------------
def load_pairs(path, lab, U, min_conf):
    """Pair feature rows + cell keys + areas, from filenames or frame ids."""
    p = pd.read_csv(path)
    if "worse_id" in p:   # QA format: worse_id/better_id (+ files), confidence
        p = p.rename(columns={"worse_id": "id_a", "better_id": "id_b",
                              "worse_file": "file_a", "better_file": "file_b",
                              "confidence": "vlm_conf"})
        p["vlm_pair"] = "A"
    p = p[p["vlm_pair"].isin(["A", "B"])]
    if "vlm_conf" in p and min_conf:
        p = p[p["vlm_conf"].map(CONF_RANK).fillna(0) >= CONF_RANK[min_conf]]
    meta = pd.read_csv(os.path.join(CACHE, "frame_meta.csv"))
    meta["file"] = meta["image_url"].fillna("").str.replace("images/", "", regex=False)
    by_file = {f: i for i, f in enumerate(lab["files"])}
    z = np.load(os.path.join(CACHE, "frame_feats_v2.npz"), allow_pickle=True)
    row_of_id = {int(i): j for j, i in enumerate(z["ids"])}
    id_of_file = dict(zip(meta["file"], meta["id"]))
    pos = meta.set_index("id")[["lat", "lon"]]

    def frame(col_file, col_id, r):
        f = r.get(col_file) if col_file in r else None
        if isinstance(f, str) and f in by_file:                    # labelled
            i = by_file[f]
            return lab["X"][i], lab["lat"][i], lab["lon"][i], lab["area"][i]
        fid = int(r[col_id]) if col_id in r and pd.notna(r.get(col_id)) else id_of_file.get(f)
        if fid is None or fid not in row_of_id or fid not in pos.index:
            return None
        from build_coords import assign_area
        la, lo = pos.loc[fid, "lat"], pos.loc[fid, "lon"]
        return (z["feats"][row_of_id[fid]].astype(np.float32), la, lo,
                assign_area(np.array([la]), np.array([lo]))[0])

    A, B, s, ck, ar = [], [], [], [], []
    dropped = 0
    for _, r in p.iterrows():
        fa, fb = frame("file_a", "id_a", r), frame("file_b", "id_b", r)
        if fa is None or fb is None:
            dropped += 1
            continue
        A.append(fa[0]); B.append(fb[0])
        s.append(1.0 if r["vlm_pair"] == "A" else -1.0)
        ck.append((cell_keys(fa[1], fa[2]), cell_keys(fb[1], fb[2])))
        ar.append((fa[3], fb[3]))
    print(f"pairs: {len(s)} usable ({dropped} without features/position) from {path}")
    return {"A": np.array(A), "B": np.array(B), "s": np.array(s),
            "ck": np.array(ck), "area": np.array(ar, dtype=object)}


def folds(lab, kind):
    if kind == "spatial":
        return S.spatial_folds(lab["yc"], lab["groups"])
    return [(np.flatnonzero(lab["area"] != a), np.flatnonzero(lab["area"] == a))
            for a in S.AREA_LABELS]


def pair_mask(P, lab, te, kind):
    """Pairs allowed in a fold whose test set is ``te``."""
    if kind == "spatial":
        bad = np.isin(P["ck"], lab["ckey"][te]).any(1)
    else:
        a = lab["area"][te][0]
        bad = (P["area"] == a).any(1)
    return ~bad


SVR_BASE = False   # set by --svr-base


def fit_pred(lab, tr, te_X, lam, P, pm):
    m = RankRidge(lam, svr_base=SVR_BASE)
    if lam > 0 and P is not None and pm.any():
        m.fit(lab["X"][tr], lab["y"][tr], P["A"][pm], P["B"][pm], P["s"][pm])
    else:
        m.fit(lab["X"][tr], lab["y"][tr])
    return m.predict(te_X)


def inner_oof(lab, tr, lam, P, pm):
    ioof = np.zeros(len(tr))
    for itr, ite in S.spatial_folds(lab["yc"][tr], lab["groups"][tr], S.INNER_SPLITS):
        # inner test cells' pairs are excluded too
        ipm = pm & ~np.isin(P["ck"], lab["ckey"][tr][ite]).any(1) if P is not None else pm
        ioof[ite] = fit_pred(lab, tr[itr], lab["X"][tr][ite], lam, P, ipm)
    return ioof


def run(lab, kind, P, lams):
    """lams: fixed list of one lam, or several -> nested selection."""
    n = len(lab["y"])
    oof, pred, chosen = np.zeros(n), np.zeros(n, int), []
    for tr, te in folds(lab, kind):
        pm = pair_mask(P, lab, te, kind) if P is not None else None
        best = None
        for lam in lams:
            io = inner_oof(lab, tr, lam, P, pm)
            ths = S.tune_thresholds(lab["yc"][tr], io)
            q = S.ordinal_metrics(lab["yc"][tr], np.digitize(io, ths) + 1, io)["qwk"]
            if best is None or q > best[0]:
                best = (q, lam, ths)
        _, lam, ths = best
        chosen.append(lam)
        oof[te] = fit_pred(lab, tr, lab["X"][te], lam, P, pm)
        pred[te] = np.digitize(oof[te], ths) + 1
    return {"oof": oof, "pred": pred, "lams": chosen}


def run_svr(lab, kind):
    n = len(lab["y"])
    oof, pred = np.zeros(n), np.zeros(n, int)
    mk = lambda: SVR(C=1.0, gamma="scale", epsilon=0.05)  # noqa: E731
    for tr, te in folds(lab, kind):
        oof[te] = S._fit_predict(mk, lab["X"][tr], lab["y"][tr], lab["X"][te])
        io = np.zeros(len(tr))
        for itr, ite in S.spatial_folds(lab["yc"][tr], lab["groups"][tr], S.INNER_SPLITS):
            io[ite] = S._fit_predict(mk, lab["X"][tr][itr], lab["y"][tr][itr], lab["X"][tr][ite])
        pred[te] = np.digitize(oof[te], S.tune_thresholds(lab["yc"][tr], io)) + 1
    return {"oof": oof, "pred": pred}


def line(name, lab, res, refs):
    yc = lab["yc"]
    m = S.ordinal_metrics(yc, res["pred"], res["oof"])
    rec2 = recall_score(yc, res["pred"], labels=[2], average=None)[0]
    b = lab["area"] == "budapest"
    mb = S.ordinal_metrics(yc[b], res["pred"][b], res["oof"][b])
    out = (f"  {name:30s} QWK={m['qwk']:.3f} MAE={m['mae']:.3f} AUC={m['bad_auc']:.3f} "
           f"rec2={rec2:.2f} BP QWK={mb['qwk']:.3f}")
    for rname, ref in refs:
        d = S.paired_bootstrap_delta(yc, ref, res, lab["groups"])
        out += (f" | vs {rname} ΔQWK {d['qwk'][0]:+.3f} [{d['qwk'][1]:+.3f},"
                f"{d['qwk'][2]:+.3f}]{'*' if d['qwk'][1] > 0 else ''}")
    if "lams" in res:
        out += f" | lam/fold {res['lams']}"
    print(out, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("--min-conf", choices=list(CONF_RANK), default=None)
    ap.add_argument("--svr-base", action="store_true",
                    help="champion SVR as the base; the ridge only learns a correction")
    args = ap.parse_args()
    global SVR_BASE
    SVR_BASE = args.svr_base
    lab, U = load()
    lab["ckey"] = cell_keys(lab["lat"], lab["lon"])
    P = load_pairs(args.pairs, lab, U, args.min_conf)
    print(f"pair frames by area: {pd.Series(P['area'].ravel()).value_counts().to_dict()}\n")
    for kind in ("spatial", "loro"):
        print(f"[{kind}]")
        svr = run_svr(lab, kind)
        line("champion SVR", lab, svr, [])
        r0 = run(lab, kind, None, [0.0])
        line(("SVR + ridge corr." if SVR_BASE else "kernel ridge") + " (lam 0, control)",
             lab, r0, [("SVR", svr)])
        for lam in LAMS[1:]:
            line(f"+ pairs, lam {lam}", lab, run(lab, kind, P, [lam]),
                 [("SVR", svr), ("lam0", r0)])
        line("+ pairs, lam nested", lab, run(lab, kind, P, LAMS),
             [("SVR", svr), ("lam0", r0)])
        print()


if __name__ == "__main__":
    main()
