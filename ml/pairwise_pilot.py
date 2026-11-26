"""Pairwise "which road is worse?" pilot for VLM judges (T-53).

Absolute 1-4 grades are noisy for VLMs (pilot QWK 0.63-0.72). This pilot asks
whether *relative* judgments ("which pavement is in worse condition, A or B?")
agree with the human order well enough to generate ranking labels at scale.

    .venv/bin/python ml/pairwise_pilot.py make  [--run run1] [--seed 20261126]
    .venv/bin/python ml/pairwise_pilot.py score [--run run1]

`make` samples ~120 pairs of labelled frames, stratified by the human grade
difference (0 / 1 / 2+), half within one region and half across regions, at
least 300 m apart (neighbouring frames are often the same panorama). Frames
are hard-linked under blind names into batches of 10 pairs:
    data/vlm/pairwise/<run>/bNN/pNNN_A.jpg, pNNN_B.jpg   (judge sees only these)
    data/vlm/pairwise/<run>/key.csv                       (never shown to judges)
Judges (fresh VLM subagents, one batch each) write
    data/vlm/pairwise/<run>/answers/bNN.json   [{"pair": "p001", "worse": "A|B|equal",
                                                  "confidence": "low|medium|high", "note": "..."}]

`score` compares the answers with the human order, with the order implied by
the absolute VLM grades of the same frames (ml/cache/vlm_attributes.csv,
rqi_guess) and with the champion model's out-of-fold scores
(ml/cache/oof_spatial_champion.csv). Grades here use the training numbering
(1 = best, 4 = worst), so the WORSE frame has the HIGHER grade / score.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
IMAGES = DATA / "images"
OUT_ROOT = DATA / "vlm" / "pairwise"
DATASET = REPO / "ml" / "cache" / "dataset_v2.csv"
OOF = REPO / "ml" / "cache" / "oof_spatial_champion.csv"
VLM_ABS = REPO / "ml" / "cache" / "vlm_attributes.csv"

PAIRS_PER_BATCH = 10
MIN_DISTANCE_M = 300.0
# Pairs per human |grade difference|.
STRATA = {0: 30, 1: 45, 2: 30, 3: 15}


# --------------------------------------------------------------------------
# Pure helpers (unit-testable)
# --------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def worse_side(a: float | None, b: float | None) -> str | None:
    """'A' / 'B' / 'equal' for grades or scores where higher = worse; None if unknown."""
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (
        isinstance(b, float) and math.isnan(b)
    ):
        return None
    if a > b:
        return "A"
    if b > a:
        return "B"
    return "equal"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for k successes out of n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def accuracy(rows: list[dict], col: str) -> dict:
    """Agreement with the human order on pairs where the human sees a difference.

    `exact`: share where `col` names the human's worse frame ("equal" counts as wrong).
    `decided`: share of pairs where `col` did not answer "equal".
    `among_decided`: accuracy over the decided pairs only.
    """
    diff = [r for r in rows if r["human"] in ("A", "B") and r.get(col) is not None]
    n = len(diff)
    k = sum(r[col] == r["human"] for r in diff)
    decided = [r for r in diff if r[col] != "equal"]
    kd = sum(r[col] == r["human"] for r in decided)
    lo, hi = wilson(k, n)
    return {
        "n": n,
        "exact": round(k / n, 3) if n else None,
        "ci95": [round(lo, 3), round(hi, 3)] if n else None,
        "decided": round(len(decided) / n, 3) if n else None,
        "among_decided": round(kd / len(decided), 3) if decided else None,
    }


# --------------------------------------------------------------------------
# make
# --------------------------------------------------------------------------

def load_frames() -> pd.DataFrame:
    ds = pd.read_csv(DATASET)[["image_filename", "rqi", "is_road_prob"]]
    oof = pd.read_csv(OOF)[["image_filename", "lat", "lon", "area", "score", "pred_rqi"]]
    vlm = pd.read_csv(VLM_ABS)[["image_filename", "road_visible", "obstruction_pct", "rqi_guess"]]
    df = ds.merge(oof, on="image_filename").merge(vlm, on="image_filename", how="left")
    ok = (
        (df.is_road_prob >= 0.5)
        & (df.road_visible.fillna("yes") == "yes")
        & (df.obstruction_pct.fillna(0) < 50)
        & df.image_filename.map(lambda f: (IMAGES / f).exists())
    )
    return df[ok].reset_index(drop=True)


def sample_pairs(df: pd.DataFrame, seed: int) -> list[tuple[int, int, int, bool]]:
    """[(row_a, row_b, |delta|, same_area)] — every frame used at most once."""
    rng = random.Random(seed)
    used: set[int] = set()
    by_grade = {g: list(df.index[df.rqi == g]) for g in (1, 2, 3, 4)}
    for g in by_grade:
        rng.shuffle(by_grade[g])
    pairs = []
    for delta, n in STRATA.items():
        grade_pairs = [(g, g + delta) for g in (1, 2, 3, 4) if g + delta <= 4]
        for i in range(n):
            ga, gb = grade_pairs[i % len(grade_pairs)]
            same_area = i % 2 == 0
            for _ in range(2000):
                a = rng.choice(by_grade[ga])
                if a in used:
                    continue
                cands = [
                    b for b in by_grade[gb]
                    if b not in used and b != a
                    and (df.area[b] == df.area[a]) == same_area
                    and haversine_m(df.lat[a], df.lon[a], df.lat[b], df.lon[b]) >= MIN_DISTANCE_M
                ]
                if not cands:
                    continue
                b = rng.choice(cands)
                used.update((a, b))
                pairs.append((a, b, delta, same_area))
                break
    rng.shuffle(pairs)
    return pairs


def make(run: str, seed: int) -> None:
    out = OUT_ROOT / run
    if out.exists():
        raise SystemExit(f"{out} exists — pick another --run")
    df = load_frames()
    pairs = sample_pairs(df, seed)
    rng = random.Random(seed + 1)
    rows = []
    for i, (a, b, delta, same_area) in enumerate(pairs):
        if rng.random() < 0.5:
            a, b = b, a
        pid = f"p{i + 1:03d}"
        batch = f"b{i // PAIRS_PER_BATCH + 1:02d}"
        bdir = out / batch
        bdir.mkdir(parents=True, exist_ok=True)
        for side, row in (("A", a), ("B", b)):
            os.link(IMAGES / df.image_filename[row], bdir / f"{pid}_{side}.jpg")
        rows.append({
            "pair": pid, "batch": batch, "delta": delta, "same_area": same_area,
            "file_a": df.image_filename[a], "file_b": df.image_filename[b],
            "area_a": df.area[a], "area_b": df.area[b],
            "human_a": int(df.rqi[a]), "human_b": int(df.rqi[b]),
            "vlm_abs_a": df.rqi_guess[a], "vlm_abs_b": df.rqi_guess[b],
            "model_a": float(df.score[a]), "model_b": float(df.score[b]),
            "distance_m": round(haversine_m(df.lat[a], df.lon[a], df.lat[b], df.lon[b])),
        })
    (out / "answers").mkdir()
    key = pd.DataFrame(rows)
    key.to_csv(out / "key.csv", index=False)
    print(f"{len(key)} pairs in {key.batch.nunique()} batches -> {out}")
    print(key.groupby(["delta", "same_area"]).size().to_string())


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------

def score(run: str) -> dict:
    out = OUT_ROOT / run
    key = pd.read_csv(out / "key.csv")
    answers = {}
    for f in sorted((out / "answers").glob("b*.json")):
        for a in json.loads(f.read_text()):
            answers[a["pair"]] = a
    rows = []
    for r in key.to_dict("records"):
        a = answers.get(r["pair"])
        rows.append({
            **r,
            "human": worse_side(r["human_a"], r["human_b"]),
            "vlm_pair": None if a is None else a["worse"],
            "vlm_conf": None if a is None else a.get("confidence"),
            "vlm_abs": worse_side(r["vlm_abs_a"], r["vlm_abs_b"]),
            "model": worse_side(r["model_a"], r["model_b"]),
        })
    answered = [r for r in rows if r["vlm_pair"] is not None]
    res = {"pairs": len(rows), "answered": len(answered), "overall": {}, "by_delta": {}}
    for col in ("vlm_pair", "vlm_abs", "model"):
        res["overall"][col] = accuracy(answered, col)
    for d in sorted(key.delta.unique()):
        if d == 0:
            continue
        sub = [r for r in answered if r["delta"] == d]
        res["by_delta"][int(d)] = {c: accuracy(sub, c) for c in ("vlm_pair", "vlm_abs", "model")}
    for scope, sub in (("same_area", [r for r in answered if r["same_area"]]),
                       ("cross_area", [r for r in answered if not r["same_area"]])):
        res[scope] = {c: accuracy(sub, c) for c in ("vlm_pair", "vlm_abs", "model")}
    for conf in ("high", "medium", "low"):
        sub = [r for r in answered if r["vlm_conf"] == conf]
        res.setdefault("vlm_pair_by_confidence", {})[conf] = accuracy(sub, "vlm_pair")
    ties = [r for r in answered if r["delta"] == 0]
    res["delta0"] = {
        "n": len(ties),
        "vlm_pair_equal": round(sum(r["vlm_pair"] == "equal" for r in ties) / len(ties), 3) if ties else None,
        "vlm_abs_equal": round(sum(r["vlm_abs"] == "equal" for r in ties) / len(ties), 3) if ties else None,
    }
    diff = [r for r in answered if r["human"] in ("A", "B")]
    agree = [r for r in diff if r["vlm_pair"] in ("A", "B")]
    res["vlm_pair_vs_model_agreement"] = (
        round(sum(r["vlm_pair"] == r["model"] for r in agree) / len(agree), 3) if agree else None
    )
    both_right = sum(r["vlm_pair"] == r["human"] and r["model"] == r["human"] for r in diff)
    vlm_only = sum(r["vlm_pair"] == r["human"] and r["model"] != r["human"] for r in diff)
    model_only = sum(r["vlm_pair"] != r["human"] and r["model"] == r["human"] for r in diff)
    res["complementarity"] = {"both_right": both_right, "vlm_only": vlm_only, "model_only": model_only,
                              "both_wrong": len(diff) - both_right - vlm_only - model_only}
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    pd.DataFrame(rows).to_csv(out / "scored.csv", index=False)
    print(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["make", "score"])
    ap.add_argument("--run", default="run1")
    ap.add_argument("--seed", type=int, default=20261126)
    args = ap.parse_args()
    if args.cmd == "make":
        make(args.run, args.seed)
    else:
        score(args.run)


if __name__ == "__main__":
    main()
