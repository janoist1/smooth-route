"""
Era 11 — how many and which new labels lift the champion (simulation only).

Uses the cached DINOv2-small cls+patch features (ml/cache/feats_v2_small.npz)
and the champion head (SVR-RBF C=1, eps=0.05), always under the official
spatial protocol of ml/spatial_cv.py: 1 km cells, StratifiedGroupKFold(5,
seed 42), cut-points tuned on inner spatial OOF of whatever the training set
is. No images are read. Labels stay in ML severity (1 = best).

Three simulations:

  curve     QWK/MAE/AUC vs share of the training labels (25/50/75/100 %),
            subsampled by whole 1 km cells (new labels = new streets) and,
            as a contrast, by single frames (denser labels on known streets).
            A saturating power law and a log-linear fit extrapolate the gain
            from +250/+500/+1000 labels.
  budapest  leave-Budapest-out: train on the three other areas plus k
            Budapest labels from OTHER Budapest cells, test on the held-out
            Budapest cell (leave-one-cell-out over Budapest 500 m cells, and
            1 km as a stricter check). k = 0/25/50/100/200, capped by the pool.
  select    which labels help most per label: start from half of the training
            cells, add a budget of frames from the other half chosen by the
            label-queue strategies (backend/app/services/label_queue.py):
            random, diverse (thinned, one per 1 km cell, emptiest cell first),
            uncertain (score nearest a cut-point, round-robin over the three
            boundaries), mixed (diverse/uncertain interleaved).

    .venv/bin/python ml/learning_curve.py [curve|budapest|select|all]
Writes ml/cache/learning_curve_<part>.json (gitignored).
"""
import json
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402
from scipy.optimize import curve_fit  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.svm import SVR  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402
from vlm_attributes import dataset  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
N_JOBS = 8
SEEDS = [0, 1, 2, 3, 4]
SEL_SEEDS = [0, 1, 2, 3, 4, 5, 6, 7]
FRACS = [0.25, 0.5, 0.75, 1.0]
EXTRA = [250, 500, 1000]
BP_K = [0, 25, 50, 100, 200]
BUDGETS = [50, 100, 150]  # the 50 m-thinned pool holds ~160-200 frames per fold
THIN_M, DUP_M = 150.0, 50.0   # same radii as the label queue


# --------------------------------------------------------------------------
# data + the one fit/evaluate primitive
# --------------------------------------------------------------------------
def load():
    feats, df = dataset()
    X = np.hstack([feats["cls"], feats["patch"]])
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    g = S.grid_cells(df["lat"].values, df["lon"].values)
    xy = np.column_stack([df["lon"].values * 111_320.0 * np.cos(np.radians(S._LAT_REF)),
                          df["lat"].values * 111_320.0])  # local metres
    return {"X": X, "y": y, "yc": yc, "g": g, "xy": xy, "df": df,
            "bp": df["area"].values == "budapest"}


def _ensure():
    """Each joblib worker loads the cached features once."""
    global D
    if D is None:
        D = load()


def _fit(X, y, tr):
    m = make_pipeline(StandardScaler(), SVR(C=1.0, gamma="scale", epsilon=0.05))
    return m.fit(X[tr], y[tr])


def fit_tuned(D, tr):
    """Champion head on rows ``tr`` + cut-points from inner spatial OOF."""
    X, y, yc, g = D["X"], D["y"], D["yc"], D["g"]
    model = _fit(X, y, tr)
    ioof = np.zeros(len(tr))
    for itr, ite in S.spatial_folds(yc[tr], g[tr], S.INNER_SPLITS, S.SEED):
        ioof[ite] = _fit(X, y, tr[itr]).predict(X[tr[ite]])
    return model, S.tune_thresholds(yc[tr], ioof)


def evaluate(D, tr, te):
    model, th = fit_tuned(D, tr)
    s = model.predict(D["X"][te])
    return s, np.digitize(s, th) + 1, th


def metrics(yc, pred, score):
    m = S.ordinal_metrics(yc, pred, score)
    return {k: round(m[k], 4) for k in ("qwk", "mae", "bad_auc", "n")}


def outer():
    return S.spatial_folds(D["yc"], D["g"], S.N_SPLITS, S.SEED)


# --------------------------------------------------------------------------
# 1. learning curve
# --------------------------------------------------------------------------
def _subsample(tr, frac, mode, rng):
    if frac >= 1.0:
        return tr
    if mode == "frame":
        return np.sort(rng.choice(tr, size=int(round(frac * len(tr))), replace=False))
    cells = np.unique(D["g"][tr])
    rng.shuffle(cells)
    # add whole cells until the frame share is reached (cells differ in size)
    keep, n = [], 0
    for c in cells:
        if n >= frac * len(tr):
            break
        keep.append(c)
        n += int((D["g"][tr] == c).sum())
    return tr[np.isin(D["g"][tr], keep)]


def _curve_job(frac, mode, seed):
    _ensure()
    rng = np.random.default_rng(seed)
    n = len(D["y"])
    oof, pred, ntr = np.zeros(n), np.zeros(n, int), []
    for tr, te in outer():
        sub = _subsample(tr, frac, mode, rng)
        ntr.append(len(sub))
        oof[te], pred[te], _ = evaluate(D, sub, te)
    return {"frac": frac, "mode": mode, "seed": seed, "n_train": float(np.mean(ntr)),
            **metrics(D["yc"], pred, oof)}


def _power(n, a, b, c):
    return a - b * np.power(n, -c)


def fit_curves(rows, metric="qwk"):
    """Fit power law + log-linear on per-fraction means; bootstrap seeds."""
    fr = sorted({r["frac"] for r in rows})

    def means(seed_pick):
        n = np.array([np.mean([r["n_train"] for r in rows if r["frac"] == f]) for f in fr])
        v = np.array([np.mean([r[metric] for r in rows if r["frac"] == f and r["seed"] in seed_pick])
                      for f in fr])
        return n, v

    sign = -1.0 if metric == "mae" else 1.0  # power law needs a rising curve

    def extrap(n, v):
        out = {}
        n100 = n[-1]
        v = sign * v
        try:
            p, _ = curve_fit(_power, n, v, p0=[v[-1] + 0.05, 1.0, 0.5],
                             bounds=([-1, 0, 0.05], [2, 1e4, 3]), maxfev=20000)
            out["power"] = {f"+{e}": float(sign * (_power(n100 + 0.8 * e, *p)
                                                   - _power(n100, *p))) for e in EXTRA}
            out["power_params"] = [float(x) for x in p]
        except RuntimeError:
            out["power"] = None
        b = np.polyfit(np.log(n), v, 1)
        out["loglin"] = {f"+{e}": float(sign * b[0] * np.log((n100 + 0.8 * e) / n100))
                         for e in EXTRA}
        out["loglin_slope_per_doubling"] = float(sign * b[0] * np.log(2))
        return out

    seeds = sorted({r["seed"] for r in rows})
    n, v = means(seeds)
    res = {"n_train": n.tolist(), metric: v.tolist(), **extrap(n, v)}
    rng = np.random.default_rng(0)
    boots = {"power": {f"+{e}": [] for e in EXTRA}, "loglin": {f"+{e}": [] for e in EXTRA}}
    for _ in range(300):
        pick = set(rng.choice(seeds, len(seeds), replace=True).tolist())
        e = extrap(*means(pick))
        for kind in boots:
            if e.get(kind):
                for k, val in e[kind].items():
                    boots[kind][k].append(val)
    res["ci"] = {kind: {k: [float(np.percentile(v_, 5)), float(np.percentile(v_, 95))]
                        for k, v_ in d.items() if v_} for kind, d in boots.items()}
    return res


def run_curve():
    jobs = [(f, m, s) for m in ("cell", "frame") for f in FRACS for s in SEEDS
            if not (f == 1.0 and s != SEEDS[0])]
    rows = Parallel(N_JOBS)(delayed(_curve_job)(*j) for j in jobs)
    full = [r for r in rows if r["frac"] == 1.0][0]
    for s in SEEDS[1:]:  # 100 % is deterministic: replicate for the fits
        for m in ("cell", "frame"):
            rows.append({**full, "mode": m, "seed": s})
    out = {"rows": rows, "fits": {}}
    for m in ("cell", "frame"):
        rr = [r for r in rows if r["mode"] == m]
        out["fits"][m] = {k: fit_curves(rr, k) for k in ("qwk", "mae", "bad_auc")}
    return out


# --------------------------------------------------------------------------
# 2. Budapest
# --------------------------------------------------------------------------
def _bp_job(k, seed, cell_m):
    _ensure()
    bp = D["bp"]
    nb = np.flatnonzero(~bp)
    gb = S.grid_cells(D["df"]["lat"].values, D["df"]["lon"].values, cell_m=cell_m)
    rng = np.random.default_rng(seed)
    n = len(D["y"])
    oof, pred, used = np.zeros(n), np.zeros(n, int), []
    for c in np.unique(gb[bp]):
        te = np.flatnonzero(bp & (gb == c))
        # added labels come from other Budapest cells, and never from within
        # 200 m of a test frame (a cell edge is not a wall)
        pool = np.flatnonzero(bp & (gb != c))
        if len(pool):
            d, _ = cKDTree(D["xy"][te]).query(D["xy"][pool])
            pool = pool[d > 200.0]
        kk = min(k, len(pool))
        used.append(kk)
        add = rng.choice(pool, size=kk, replace=False) if kk else np.array([], int)
        tr = np.concatenate([nb, add]).astype(int)
        oof[te], pred[te], _ = evaluate(D, tr, te)
    m = np.flatnonzero(bp)
    return {"k": k, "seed": seed, "cell_m": cell_m, "k_used_mean": float(np.mean(used)),
            "n_test_cells": int(len(used)),
            **metrics(D["yc"][m], pred[m], oof[m])}


def run_budapest():
    jobs = [(k, s, cm) for cm in (500, 1000) for k in BP_K
            for s in (SEEDS if k else SEEDS[:1])]
    rows = Parallel(N_JOBS)(delayed(_bp_job)(*j) for j in jobs)
    summ = {}
    for cm in (500, 1000):
        for k in BP_K:
            rr = [r for r in rows if r["cell_m"] == cm and r["k"] == k]
            summ[f"{cm}m_k{k}"] = {
                "k_used": round(float(np.mean([r["k_used_mean"] for r in rr])), 1),
                **{mt: [round(float(np.mean([r[mt] for r in rr])), 4),
                        round(float(np.std([r[mt] for r in rr])), 4)]
                   for mt in ("qwk", "mae", "bad_auc")}}
    # reference: Budapest frames inside the official 5-fold spatial CV
    oof, pred = np.zeros(len(D["y"])), np.zeros(len(D["y"]), int)
    for tr, te in outer():
        oof[te], pred[te], _ = evaluate(D, tr, te)
    m = np.flatnonzero(D["bp"])
    summ["official_cv_budapest"] = metrics(D["yc"][m], pred[m], oof[m])
    return {"rows": rows, "summary": summ}


# --------------------------------------------------------------------------
# 3. selection strategies
# --------------------------------------------------------------------------
def _thin(cand, xy, rng, radius, avoid=None):
    """Greedy thinning in random order; also >= DUP_M from ``avoid`` rows."""
    order = rng.permutation(cand)
    kept, tree_pts = [], [] if avoid is None else list(xy[avoid])
    for i in order:
        if tree_pts:
            d = np.min(np.hypot(*(np.asarray(tree_pts) - xy[i]).T))
            if d < radius:
                continue
        kept.append(i)
        tree_pts.append(xy[i])
    return np.array(kept, int)


def _pick_random(pool, budget, rng, **_):
    return rng.choice(pool, size=min(budget, len(pool)), replace=False)


def _pick_random_dense(pool, budget, rng, dense, **_):
    """Random over ALL pool frames, consecutive ~10 m neighbours included
    (what labelling a drive frame by frame looks like)."""
    return rng.choice(dense, size=min(budget, len(dense)), replace=False)


def _pick_diverse(pool, budget, rng, labelled, **_):
    xy, g = D["xy"], D["g"]
    cand = _thin(pool, xy, rng, THIN_M)
    counts = {c: int((g[labelled] == c).sum()) for c in np.unique(g[cand])}
    by_cell = {c: list(rng.permutation(cand[g[cand] == c])) for c in counts}
    picks = []
    while len(picks) < budget and any(by_cell.values()):
        for c in sorted(by_cell, key=lambda c: (counts[c], rng.random())):
            if by_cell[c] and len(picks) < budget:
                picks.append(by_cell[c].pop())
                counts[c] += 1
    # thinning can leave fewer than the budget: top up at random
    if len(picks) < budget:
        rest = np.setdiff1d(pool, picks)
        picks += list(rng.choice(rest, size=min(budget - len(picks), len(rest)), replace=False))
    return np.array(picks, int)


def _pick_uncertain(pool, budget, rng, score, th, **_):
    xy = D["xy"]
    lists = [list(pool[np.argsort(np.abs(score - t) + 1e-9 * rng.random(len(pool)))])
             for t in th]
    picks, pts = [], []
    while len(picks) < budget and any(lists):
        for lst in lists:
            while lst:
                i = lst.pop(0)
                if i in picks:
                    continue
                if pts and np.min(np.hypot(*(np.asarray(pts) - xy[i]).T)) < DUP_M:
                    continue
                picks.append(i)
                pts.append(xy[i])
                break
            if len(picks) >= budget:
                break
    return np.array(picks, int)


def _pick_mixed(pool, budget, rng, **kw):
    d = _pick_diverse(pool, budget, rng, **kw)
    u = _pick_uncertain(pool, budget, rng, **kw)
    picks = []
    for a, b in zip(d, u):
        for i in (a, b):
            if i not in picks and len(picks) < budget:
                picks.append(i)
    return np.array(picks, int)


STRATEGIES = {"random_dense": _pick_random_dense, "random": _pick_random,
              "diverse": _pick_diverse,
              "uncertain": _pick_uncertain, "mixed": _pick_mixed}


def _select_job(seed):
    """One seed: per outer fold a 50 % seed set of cells, then every
    strategy x budget, plus the seed-only and all-pool references.

    Every strategy except random_dense draws from the same candidate set: the
    pool thinned to frames >= DUP_M apart (the label queue never offers two
    frames closer than that), so all budgets are equal-sized."""
    _ensure()
    rng = np.random.default_rng(1000 + seed)
    n = len(D["y"])
    names = ["seed_only", "all_pool"] + [f"{s}_{b}" for s in STRATEGIES for b in BUDGETS]
    oof = {k: np.zeros(n) for k in names}
    pred = {k: np.zeros(n, int) for k in names}
    sizes = {k: [] for k in names}
    n_cand = []
    for tr, te in outer():
        cells = np.unique(D["g"][tr])
        rng.shuffle(cells)
        seed_cells = cells[: len(cells) // 2]
        lab = tr[np.isin(D["g"][tr], seed_cells)]
        dense = tr[~np.isin(D["g"][tr], seed_cells)]
        pool = _thin(dense, D["xy"], rng, DUP_M)
        n_cand.append(len(pool))
        model, th = fit_tuned(D, lab)
        score = model.predict(D["X"][pool])
        for key, rows in (("seed_only", lab), ("all_pool", tr)):
            oof[key][te], pred[key][te], _ = evaluate(D, rows, te)
            sizes[key].append(len(rows))
        for s, fn in STRATEGIES.items():
            for b in BUDGETS:
                sel = fn(pool, b, np.random.default_rng(seed * 7 + b), labelled=lab,
                         score=score, th=th, dense=dense)
                rows = np.concatenate([lab, sel]).astype(int)
                key = f"{s}_{b}"
                oof[key][te], pred[key][te], _ = evaluate(D, rows, te)
                sizes[key].append(len(rows))
    out = {}
    for k in names:
        out[k] = {**metrics(D["yc"], pred[k], oof[k]), "n_train": float(np.mean(sizes[k]))}
        # class-wise recall on the official 4 classes
        out[k]["recall"] = [round(float(np.mean(pred[k][D["yc"] == c] == c)), 3)
                            for c in S.RQI_LABELS]
    return {"seed": seed, "res": out, "n_candidates": n_cand}


def run_select():
    rows = Parallel(N_JOBS)(delayed(_select_job)(s) for s in SEL_SEEDS)
    keys = list(rows[0]["res"])
    summ = {}
    for k in keys:
        q = np.array([r["res"][k]["qwk"] for r in rows])
        summ[k] = {"qwk": round(float(q.mean()), 4), "qwk_sd": round(float(q.std()), 4),
                   "mae": round(float(np.mean([r["res"][k]["mae"] for r in rows])), 4),
                   "bad_auc": round(float(np.mean([r["res"][k]["bad_auc"] for r in rows])), 4),
                   "n_train": round(float(np.mean([r["res"][k]["n_train"] for r in rows])), 1),
                   "recall": np.mean([r["res"][k]["recall"] for r in rows], 0).round(3).tolist()}
    # paired deltas vs random at the same budget (same seed set, same folds)
    for s in STRATEGIES:
        if s == "random":
            continue
        for b in BUDGETS:
            d = np.array([r["res"][f"{s}_{b}"]["qwk"] - r["res"][f"random_{b}"]["qwk"]
                          for r in rows])
            summ[f"{s}_{b}"]["dqwk_vs_random"] = [round(float(d.mean()), 4),
                                                  round(float(d.std(ddof=1) / np.sqrt(len(d))), 4),
                                                  int((d > 0).sum())]
    summ["n_candidates_per_fold"] = float(np.mean([r["n_candidates"] for r in rows]))
    return {"rows": rows, "summary": summ, "n_seeds": len(rows)}


# --------------------------------------------------------------------------
def main(parts):
    _ensure()
    for p in parts:
        res = {"curve": run_curve, "budapest": run_budapest, "select": run_select}[p]()
        path = os.path.join(CACHE, f"learning_curve_{p}.json")
        with open(path, "w") as fh:
            json.dump(res, fh, indent=1, default=float)
        print(p, "->", os.path.relpath(path))
        print(json.dumps(res.get("summary", res.get("fits")), indent=1, default=float)[:6000])


D = None
if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    main(["curve", "budapest", "select"] if arg == "all" else [arg])
