"""Pairwise "which road is worse?" pilot for VLM judges (T-53).

Absolute 1-4 grades are noisy for VLMs (pilot QWK 0.63-0.72). This pilot asks
whether *relative* judgments ("which pavement is in worse condition, A or B?")
agree with the human order well enough to generate ranking labels at scale.

    .venv/bin/python ml/pairwise_pilot.py make  [--run run1] [--seed 20261126]
    .venv/bin/python ml/pairwise_pilot.py score [--run run1]
    .venv/bin/python ml/pairwise_pilot.py make-unsure   [--run unsure1] [--n 300]
    .venv/bin/python ml/pairwise_pilot.py export-unsure [--run unsure1]

`make-unsure` (T-64) builds pairs of UNLABELLED usable frames outside Budapest
where the champion is unsure: both severity scores within UNSURE_BAND of the
same 2|3 or 3|4 cut-point and within MAX_SCORE_GAP of each other, >= 200 m
apart, half within one ~25 km area cell and half across. Severity = 6 - the
DB's dino_score (the DB is on the 5 = best scale since Alembic 0006); the
cut-points are the live artifact's thresholds (severity numbering).
`export-unsure` writes data/vlm/pairwise/unsure_pairs.csv with the confident
(high/medium) judgments only.

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
# Unsure pairs (T-64).
UNSURE_BAND = 0.25          # |severity - cut| for "the model is unsure"
MAX_SCORE_GAP = 0.4         # |severity_a - severity_b|
UNSURE_MIN_DISTANCE_M = 200.0
AREA_CELL_DEG = 0.25        # ~25 km cells for "same area"
# Budapest (and its agglomeration edge): the pilot was not reliable there.
BUDAPEST_BBOX = (47.35, 18.90, 47.62, 19.35)  # min_lat, min_lng, max_lat, max_lng
MODEL_ARTIFACT = REPO / "ml" / "cache" / "rqi_model.joblib"
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


# --------------------------------------------------------------------------
# make-unsure / export-unsure (T-64)
# --------------------------------------------------------------------------

def nearest_cut(severity: float, cuts: list[float]) -> tuple[float, float]:
    """(cut, |severity - cut|) for the closest cut-point."""
    cut = min(cuts, key=lambda c: abs(severity - c))
    return cut, abs(severity - cut)


def in_bbox(lat: float, lng: float, bbox=BUDAPEST_BBOX) -> bool:
    return bbox[0] <= lat <= bbox[2] and bbox[1] <= lng <= bbox[3]


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return "postgresql://postgres:postgres@localhost:5433/smooth_route"


def load_unsure_frames(cuts: list[float]) -> pd.DataFrame:
    import psycopg2

    conn = psycopg2.connect(_db_url())
    conn.set_session(readonly=True)
    labelled = set(pd.read_csv(DATASET).image_filename)
    cur = conn.cursor()
    cur.execute("SELECT image_filename FROM training_data WHERE manual_rqi IS NOT NULL")
    labelled |= {r[0] for r in cur.fetchall()}
    cur.execute(
        """SELECT id, image_url, latitude, longitude, (analysis_metadata->>'dino_score')::float
           FROM street_view_images
           WHERE image_url LIKE 'images/%%'
             AND analysis_metadata->>'dino_score' IS NOT NULL
             AND coalesce(analysis_metadata->'frame_quality'->>'usable', 'false') = 'true'"""
    )
    rows = []
    for fid, url, lat, lng, score in cur.fetchall():
        fname = url.split("/", 1)[1]
        if fname in labelled or in_bbox(lat, lng) or not (IMAGES / fname).exists():
            continue
        severity = 6.0 - score
        cut, dist = nearest_cut(severity, cuts)
        if dist <= UNSURE_BAND:
            rows.append({"id": fid, "file": fname, "lat": lat, "lng": lng, "severity": severity,
                         "cut": cut, "area": f"{int(lat // AREA_CELL_DEG)}_{int(lng // AREA_CELL_DEG)}"})
    conn.close()
    return pd.DataFrame(rows)


def make_unsure(run: str, n: int, seed: int) -> None:
    import joblib

    out = OUT_ROOT / run
    if out.exists():
        raise SystemExit(f"{out} exists — pick another --run")
    thresholds = list(joblib.load(MODEL_ARTIFACT)["thresholds"])
    cuts = thresholds[1:]  # 2|3 and 3|4 (severity numbering)
    df = load_unsure_frames(cuts)
    print(f"unsure unlabelled usable frames outside Budapest: {len(df)} "
          f"(cuts {[round(c, 3) for c in cuts]}, areas {df.area.nunique()})")
    rng = random.Random(seed)
    order = list(df.index)
    rng.shuffle(order)
    used: set[int] = set()
    pairs = []
    for want_same in [i % 2 == 0 for i in range(n * 3)]:
        if len(pairs) >= n:
            break
        for a in order:
            if a in used:
                continue
            cands = [
                b for b in order
                if b not in used and b != a
                and df.cut[b] == df.cut[a]
                and abs(df.severity[a] - df.severity[b]) <= MAX_SCORE_GAP
                and (df.area[b] == df.area[a]) == want_same
                and haversine_m(df.lat[a], df.lng[a], df.lat[b], df.lng[b]) >= UNSURE_MIN_DISTANCE_M
            ]
            if not cands:
                continue
            b = rng.choice(cands)
            used.update((a, b))
            pairs.append((a, b, want_same))
            break
    rng.shuffle(pairs)
    rows = []
    for i, (a, b, same) in enumerate(pairs):
        if rng.random() < 0.5:
            a, b = b, a
        pid = f"u{i + 1:03d}"
        batch = f"b{i // PAIRS_PER_BATCH + 1:02d}"
        bdir = out / batch
        bdir.mkdir(parents=True, exist_ok=True)
        for side, r in (("A", a), ("B", b)):
            os.link(IMAGES / df.file[r], bdir / f"{pid}_{side}.jpg")
        rows.append({
            "pair": pid, "batch": batch, "same_area": same, "cut": round(df.cut[a], 3),
            "id_a": int(df.id[a]), "id_b": int(df.id[b]), "file_a": df.file[a], "file_b": df.file[b],
            "severity_a": round(df.severity[a], 3), "severity_b": round(df.severity[b], 3),
            "area_a": df.area[a], "area_b": df.area[b],
            "distance_m": round(haversine_m(df.lat[a], df.lng[a], df.lat[b], df.lng[b])),
        })
    (out / "answers").mkdir()
    key = pd.DataFrame(rows)
    key.to_csv(out / "key.csv", index=False)
    print(f"{len(key)} pairs in {key.batch.nunique()} batches -> {out}")
    print(key.groupby(["cut", "same_area"]).size().to_string())


def export_unsure(run: str) -> Path:
    out = OUT_ROOT / run
    key = pd.read_csv(out / "key.csv")
    answers = {}
    for f in sorted((out / "answers").glob("b*.json")):
        for a in json.loads(f.read_text()):
            answers[a["pair"]] = a
    rows = []
    for r in key.to_dict("records"):
        a = answers.get(r["pair"])
        if a is None or a.get("confidence") not in ("high", "medium") or a.get("worse") not in ("A", "B"):
            continue
        worse_is_a = a["worse"] == "A"
        rows.append({
            "pair": r["pair"],
            "worse_id": r["id_a"] if worse_is_a else r["id_b"],
            "better_id": r["id_b"] if worse_is_a else r["id_a"],
            "worse_file": r["file_a"] if worse_is_a else r["file_b"],
            "better_file": r["file_b"] if worse_is_a else r["file_a"],
            "confidence": a["confidence"],
            "model_severity_worse": r["severity_a"] if worse_is_a else r["severity_b"],
            "model_severity_better": r["severity_b"] if worse_is_a else r["severity_a"],
            "cut": r["cut"], "same_area": r["same_area"], "note": a.get("note", ""),
        })
    path = OUT_ROOT / "unsure_pairs.csv"
    res = pd.DataFrame(rows)
    res.to_csv(path, index=False)
    total = len(answers)
    agree = int((res.model_severity_worse > res.model_severity_better).sum()) if len(res) else 0
    print(f"answered {total}/{len(key)}; kept {len(res)} confident pairs -> {path}")
    if len(res):
        print(f"model already orders {agree}/{len(res)} ({agree / len(res):.0%}) of the kept pairs the same way")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["make", "score", "make-unsure", "export-unsure"])
    ap.add_argument("--run", default="run1")
    ap.add_argument("--seed", type=int, default=20261126)
    ap.add_argument("--n", type=int, default=300, help="make-unsure: number of pairs")
    args = ap.parse_args()
    if args.cmd == "make":
        make(args.run, args.seed)
    elif args.cmd == "score":
        score(args.run)
    elif args.cmd == "make-unsure":
        make_unsure(args.run, args.n, args.seed)
    else:
        export_unsure(args.run)


if __name__ == "__main__":
    main()
