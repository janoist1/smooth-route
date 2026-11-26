#!/usr/bin/env python3
"""Bradley-Terry scores from pairwise "which is worse?" judgments + absolute labels.

QA's pilot: relative judgments are more consistent than absolute grades. This
fits one latent severity per frame (1 = best, the ML orientation) from
  - pair_judgments (quick-rate pairwise mode):
        P(A judged worse than B) = sigmoid(s_A - s_B);  "EQUAL" = half a win each,
  - absolute human labels as a Gaussian prior  s ~ N(label, 1 / LABEL_WEIGHT),
  - the live model score as a weak prior        s ~ N(model, 1 / MODEL_WEIGHT)
    (only for frames without a label; frames with neither get the mean).
MAP estimate by gradient descent (numpy only). Output for training
experiments (no promotion): ml/cache/pairwise_scores.csv with
image_filename, svi_id, bt_score (severity), n_pairs, label_sev, model_sev.

Usage: .venv/bin/python ml/pairwise_scores.py   (needs the DB: docker compose up -d db)
"""
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ml", "cache", "pairwise_scores.csv")
SCORE_CACHE = os.path.join(ROOT, "data", "cache", "frame_scores.csv")
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5433/smooth_route")

LABEL_WEIGHT = 1.0
MODEL_WEIGHT = 0.2
RESULT_WIN = {"A": 1.0, "B": 0.0, "EQUAL": 0.5}  # share of "A is worse"


def fit_scores(n, pairs, priors, steps=2000, lr=0.05):
    """pairs: [(i, j, y)] with y = P-target that i is worse than j (1, 0, 0.5).
    priors: {i: (mean, weight)}. Returns latent severities (np.ndarray, len n)."""
    mu = np.zeros(n)
    w = np.zeros(n)
    for i, (m, wt) in priors.items():
        mu[i], w[i] = m, wt
    default = float(np.average(mu, weights=w)) if w.sum() > 0 else 0.0
    mu[w == 0] = default
    w = np.where(w == 0, 1e-3, w)  # keeps unconnected frames identified
    s = mu.copy()
    if pairs:
        ia = np.array([p[0] for p in pairs])
        ib = np.array([p[1] for p in pairs])
        y = np.array([p[2] for p in pairs], dtype=float)
    for _ in range(steps):
        grad = w * (s - mu)
        if pairs:
            p = 1.0 / (1.0 + np.exp(-(s[ia] - s[ib])))
            g = p - y  # d(-loglik)/d(s_a - s_b)
            np.add.at(grad, ia, g)
            np.add.at(grad, ib, -g)
        s -= lr * grad
    return s


def main():
    import psycopg2

    sys.path.insert(0, os.path.join(ROOT, "ml"))
    from rqi_scale import SCALE  # canonical <-> severity

    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT frame_a_id, frame_b_id, result FROM pair_judgments")
        judgments = cur.fetchall()
        if not judgments:
            print("No pair judgments yet (quick-rate page, pairwise mode).")
            return 0
        ids = sorted({a for a, _, _ in judgments} | {b for _, b, _ in judgments})
        cur.execute("SELECT svi.id, substring(svi.image_url from '[^/]+$'), td.manual_rqi "
                    "FROM street_view_images svi LEFT JOIN training_data td "
                    "ON svi.image_url = 'images/' || td.image_filename WHERE svi.id = ANY(%s)",
                    (ids,))
        rows = {i: (name, rqi) for i, name, rqi in cur.fetchall()}
    model = {}
    if os.path.exists(SCORE_CACHE):
        with open(SCORE_CACHE) as fh:
            model = {r["image_filename"]: float(r["score"]) for r in csv.DictReader(fh) if r["score"]}
    index = {fid: k for k, fid in enumerate(ids)}
    priors, n_pairs = {}, np.zeros(len(ids), dtype=int)
    for fid in ids:
        name, rqi = rows.get(fid, (None, None))
        if rqi is not None:
            priors[index[fid]] = (float(SCALE.to_severity(rqi)), LABEL_WEIGHT)
        elif name in model:  # raw model output is already severity (1 = best)
            priors[index[fid]] = (model[name], MODEL_WEIGHT)
    pairs = []
    for a, b, res in judgments:
        pairs.append((index[a], index[b], RESULT_WIN[res]))
        n_pairs[index[a]] += 1
        n_pairs[index[b]] += 1
    s = fit_scores(len(ids), pairs, priors)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["image_filename", "svi_id", "bt_score", "n_pairs", "label_sev", "model_sev"])
        for fid in ids:
            name, rqi = rows.get(fid, (None, None))
            wr.writerow([name, fid, round(float(s[index[fid]]), 4), int(n_pairs[index[fid]]),
                         "" if rqi is None else SCALE.to_severity(rqi), model.get(name, "")])
    print(f"{len(judgments)} judgments over {len(ids)} frames -> {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
