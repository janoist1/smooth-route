"""Re-score Street View frames with the LIVE RQI artifact (DINO).

Usage (from backend/):
    HF_HUB_OFFLINE=1 ../.venv/bin/python scripts/rescore_dino.py
        [--dry-run] [--limit N] [--min-id ID] [--chunk 200] [--include-unusable] [--force]
        [--save-features PATH] [--features-only]

Why: frames analysed before the v2 artifact only carry the ordinal class
(``dino_rqi_score``); the road-segment layer wants the continuous score. This
runs the product's own inference path (``app.services.dino_service`` — one
forward pass per RAW image, local device, no preprocessing) over the stored
images and writes, per frame:

- ``analysis_metadata.dino_score``     continuous estimate (3 decimals)
- ``analysis_metadata.dino_p_bad``     calibrated P(bad) (3 decimals)
- ``dino_rqi_score``                   class via the artifact's tuned cut points
- ``analysis_metadata.dino_rqi_score_prev``  the class the frame had BEFORE
  the first re-score (never overwritten afterwards — traceability)
- ``analysis_metadata.dino_artifact`` / ``dino_model_version``  which artifact
  produced the numbers; this is also the resume marker

Properties:
- Resumable: frames already carrying the current artifact's marker are
  skipped, results are committed per chunk — an interrupt loses at most one
  chunk. ``--force`` re-scores them anyway.
- Frames marked ``analysis_metadata.frame_quality.usable = false`` are left
  alone unless ``--include-unusable``.
- The metadata is merged in SQL (``jsonb ||``), so keys written concurrently
  by other tools are never overwritten with a stale copy.
- ``--dry-run`` scores and reports but writes nothing (no DB, no log).
- Every written frame is appended to ``data/rescore/dino_rescore_<artifact>.csv``
  (id, old class, old score, new score, new class, new P(bad)); the class-shift
  table printed at the end is computed from that log, i.e. over ALL runs.

Feature vectors: ``--save-features PATH`` also stores, for every frame
processed, the exact vector the head sees (the artifact's feature recipe;
768-d for v2) in an ``.npz`` — arrays ``ids`` (int32), ``feats`` (float16,
N×D), ``usable`` (bool), plus ``artifact`` / ``recipe`` / ``keys``. Score and
vector come from the same forward pass. An existing file from the same
artifact is updated by id. ``--features-only`` walks EVERY frame that has an
image (usable or not, already re-scored or not), writes nothing to the DB,
and checks each score against the re-score log.

Take a DB backup first. The model file is only read. ``HF_HUB_OFFLINE=1``
keeps the backbone load on the local Hugging Face cache (no network).
Afterwards rebuild the segments: ``scripts/build_segments.py``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_FIELDS = ["id", "old_rqi", "old_score", "new_score", "new_rqi", "new_p_bad"]

UPDATE_SQL = """
    UPDATE street_view_images
    SET analysis_metadata = (
            COALESCE(analysis_metadata::jsonb, '{}'::jsonb)
            || CASE
                 WHEN jsonb_exists(COALESCE(analysis_metadata::jsonb, '{}'::jsonb),
                                   'dino_rqi_score_prev')
                 THEN '{}'::jsonb
                 ELSE jsonb_build_object('dino_rqi_score_prev', dino_rqi_score)
               END
            || CAST(:patch AS jsonb)
        )::json,
        dino_rqi_score = :rqi
    WHERE id = :id
"""


# --------------------------------------------------------------------------
# Pure helpers (unit-tested, torch-free)
# --------------------------------------------------------------------------

def artifact_id(path: Path | str) -> str:
    """Short content hash of the artifact file — changes when it is retrained."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def is_done(dino_score: Any, dino_artifact: Any, current_artifact: str) -> bool:
    """Already re-scored with THIS artifact? (the resume marker)"""
    return dino_score is not None and dino_artifact == current_artifact


def metadata_patch(
    score: float, p_bad: Optional[float], artifact: str, version: Any, timestamp: str
) -> dict:
    """The keys merged into analysis_metadata — the same ones the product's
    DINO analysis writes, plus the artifact marker."""
    patch = {
        "dino_strategy": "DINO Classification",
        "dino_score": round(float(score), 3),
        "dino_timestamp": timestamp,
        "dino_artifact": artifact,
        "dino_model_version": version,
    }
    if p_bad is not None:
        patch["dino_p_bad"] = round(float(p_bad), 3)
    return patch


def _class_label(value: Any) -> str:
    if value in (None, ""):
        return "-"
    number = float(value)
    return str(int(number)) if number == int(number) else str(number)


def shift_table(pairs: Iterable[tuple[Any, Any]]) -> list[str]:
    """Old class → new class confusion as printable lines."""
    counts: Counter = Counter((_class_label(old), _class_label(new)) for old, new in pairs)
    if not counts:
        return ["(no frames)"]
    olds = sorted({o for o, _ in counts})
    news = sorted({n for _, n in counts})
    total = sum(counts.values())
    same = sum(v for (o, n), v in counts.items() if o == n)
    lines = ["old \\ new " + "".join(f"{n:>8}" for n in news) + f"{'total':>9}"]
    for o in olds:
        row = [counts.get((o, n), 0) for n in news]
        lines.append(f"{o:>9} " + "".join(f"{v:>8}" for v in row) + f"{sum(row):>9}")
    lines.append(f"unchanged: {same}/{total} ({100.0 * same / total:.1f} %)")
    return lines


def merge_features(existing: Optional[dict], new: dict) -> dict:
    """Combine two ``{id: (vector, usable)}`` maps; ``new`` wins per id."""
    merged = dict(existing or {})
    merged.update(new)
    return merged


def save_features(path: Path, by_id: dict, artifact: str, recipe: Any, keys: Any) -> int:
    """Write ``{id: (vector, usable)}`` as a compressed .npz, sorted by id.
    Merges with an existing file of the SAME artifact; a file from another
    artifact is replaced (its vectors would not be comparable)."""
    import numpy as np

    path = Path(path)
    existing = None
    if path.is_file():
        with np.load(path, allow_pickle=False) as old:
            if str(old["artifact"]) == artifact:
                existing = {
                    int(i): (vec, bool(u))
                    for i, vec, u in zip(old["ids"], old["feats"], old["usable"])
                }
    merged = merge_features(existing, by_id)
    ids = sorted(merged)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez_compressed(
        tmp,
        ids=np.asarray(ids, dtype=np.int32),
        feats=np.stack([np.asarray(merged[i][0], dtype=np.float16) for i in ids])
        if ids else np.zeros((0, 0), dtype=np.float16),
        usable=np.asarray([merged[i][1] for i in ids], dtype=bool),
        artifact=np.asarray(artifact),
        recipe=np.asarray(str(recipe)),
        keys=np.asarray([str(k) for k in (keys or [])]),
    )
    os.replace(tmp, path)
    return len(ids)


def read_log(path: Path) -> list[dict]:
    """The LAST logged row per frame id (a --force re-run appends again)."""
    if not path.is_file():
        return []
    latest: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            first = latest.get(row["id"])
            if first is not None:
                # Keep the ORIGINAL old values: the shift we report is from
                # before the first re-score to the latest numbers.
                row["old_rqi"], row["old_score"] = first["old_rqi"], first["old_score"]
            latest[row["id"]] = row
    return list(latest.values())


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="score and report, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="max frames this run (0 = all)")
    ap.add_argument("--min-id", type=int, default=0, help="only frames with id >= this")
    ap.add_argument("--chunk", type=int, default=200, help="frames per commit")
    ap.add_argument("--include-unusable", action="store_true",
                    help="also re-score frames marked frame_quality.usable = false")
    ap.add_argument("--force", action="store_true",
                    help="re-score frames already done with this artifact")
    ap.add_argument("--save-features", default=None, metavar="PATH",
                    help="also store each processed frame's feature vector in this .npz")
    ap.add_argument("--features-only", action="store_true",
                    help="only extract features for every frame with an image; no DB writes")
    args = ap.parse_args()
    if args.features_only and not args.save_features:
        ap.error("--features-only needs --save-features PATH")
    read_only = args.dry_run or args.features_only

    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.core.paths import data_path, resolve_stored_image
    from app.core.timeutil import utcnow
    from app.services.dino_service import MODEL_PATH, dino_service
    from app.services.segment_aggregation import frame_usable

    artifact = artifact_id(MODEL_PATH)
    dino_service.load_model()  # fail here, loudly, if the model cannot be loaded
    info = dino_service.model_info() or {}
    version = info.get("version")
    print(f"artifact {artifact} (version {version}, thresholds "
          f"{[round(float(t), 3) for t in (dino_service.thresholds if dino_service.thresholds is not None else [])]}) "
          f"on {dino_service.device}"
          f"{' — DRY RUN' if args.dry_run else ''}"
          f"{' — FEATURES ONLY (no DB writes)' if args.features_only else ''}")

    db = SessionLocal()
    try:
        rows = db.execute(text(
            """
            SELECT id, image_url, dino_rqi_score,
                   analysis_metadata->>'dino_score' AS dino_score,
                   analysis_metadata->>'dino_artifact' AS dino_artifact,
                   analysis_metadata->'frame_quality'->>'usable' AS usable
            FROM street_view_images
            WHERE image_url IS NOT NULL
            ORDER BY id
            """
        )).fetchall()

        skipped: Counter = Counter()
        todo = []
        for r in rows:
            usable = frame_usable({"frame_quality": {"usable": r.usable}})
            if r.id < args.min_id:
                skipped["below --min-id"] += 1
            elif args.features_only:
                todo.append(r)                 # every frame, whatever its state
            elif not args.include_unusable and not usable:
                skipped["unusable"] += 1
            elif not args.force and is_done(r.dino_score, r.dino_artifact, artifact):
                skipped["already done"] += 1
            else:
                todo.append(r)
        if args.limit:
            todo = todo[: args.limit]
        print(f"frames with an image: {len(rows)}; to re-score now: {len(todo)}; "
              f"skipped: {dict(skipped)}")

        log_path = data_path("rescore", f"dino_rescore_{artifact}.csv")
        log_file = writer = None
        if not read_only and todo:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not log_path.exists()
            log_file = open(log_path, "a", newline="", encoding="utf-8")
            writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
            if new_file:
                writer.writeheader()

        outcome: Counter = Counter()
        this_run: list[dict] = []
        features: dict = {}                    # id -> (float16 vector, usable)
        started = time.monotonic()
        try:
            for start in range(0, len(todo), args.chunk):
                chunk = todo[start: start + args.chunk]
                chunk_rows: list[dict] = []
                for r in chunk:
                    path = resolve_stored_image(r.image_url)
                    if path is None:
                        outcome["image file missing"] += 1
                        continue
                    if args.save_features:
                        # Score and vector from the SAME forward pass.
                        feat = dino_service.extract_features(str(path))
                        score = None if feat is None else dino_service.score_from_features(feat)
                        if feat is not None:
                            features[r.id] = (
                                feat[0].astype("float16"),
                                frame_usable({"frame_quality": {"usable": r.usable}}),
                            )
                    else:
                        score = dino_service.predict_score(str(path))
                    if score is None:
                        outcome["inference failed"] += 1
                        continue
                    rqi = dino_service.rqi_from_score(score)
                    p_bad = dino_service.p_bad_from_score(score)
                    outcome["re-scored"] += 1
                    entry = {
                        "id": r.id,
                        "old_rqi": "" if r.dino_rqi_score is None else r.dino_rqi_score,
                        "old_score": "" if r.dino_score is None else r.dino_score,
                        "new_score": round(float(score), 3),
                        "new_rqi": rqi,
                        "new_p_bad": "" if p_bad is None else round(float(p_bad), 3),
                    }
                    chunk_rows.append(entry)
                    if not read_only:
                        db.execute(text(UPDATE_SQL), {
                            "id": r.id,
                            "rqi": float(rqi),
                            "patch": json.dumps(
                                metadata_patch(score, p_bad, artifact, version, str(utcnow()))
                            ),
                        })
                if not read_only:
                    db.commit()
                    writer.writerows(chunk_rows)   # logged only once committed
                    log_file.flush()
                this_run.extend(chunk_rows)
                done = start + len(chunk)
                rate = done / max(1e-6, time.monotonic() - started)
                eta = (len(todo) - done) / max(1e-6, rate)
                print(f"  {done}/{len(todo)}  {rate:.1f} frames/s  ETA {eta / 60:.1f} min  "
                      f"{dict(outcome)}", flush=True)
        finally:
            if log_file is not None:
                log_file.close()
            if args.save_features and features:
                # Also on an interrupt: keep what was extracted so far.
                recipe = dino_service.recipe or {}
                total = save_features(Path(args.save_features), features, artifact,
                                      recipe.get("name"), recipe.get("keys"))
                dim = len(next(iter(features.values()))[0])
                print(f"features: {len(features)} vectors ({dim}-d, float16) saved, "
                      f"{total} in {args.save_features}", flush=True)
    finally:
        db.close()

    print("summary:", dict(outcome), f"in {(time.monotonic() - started) / 60:.1f} min")
    if args.features_only:
        # The DB may be mid-migration (scale flip), the re-score log is not:
        # check the scores of this pass against what the re-score wrote.
        logged = {int(r["id"]): float(r["new_score"]) for r in read_log(log_path)}
        checked = [abs(logged[r["id"]] - r["new_score"]) for r in this_run if r["id"] in logged]
        if checked:
            within = sum(1 for d in checked if d <= 0.0015)
            print(f"scores vs re-score log: {within}/{len(checked)} identical "
                  f"(max |Δ| {max(checked):.3f})")
        return
    report = this_run if args.dry_run else read_log(log_path)
    scope = "this dry run" if args.dry_run else f"all runs, {log_path}"
    print(f"class shift old → new ({len(report)} frames; {scope}):")
    print("\n".join(shift_table((r["old_rqi"], r["new_rqi"]) for r in report)))
    # Frames that already had a continuous score from this model family:
    # the new score should reproduce it.
    repeats = [abs(float(r["old_score"]) - float(r["new_score"]))
               for r in report if r["old_score"] not in ("", None)]
    if repeats:
        within = sum(1 for d in repeats if d <= 0.0015)
        print(f"frames that already had dino_score: {len(repeats)}; reproduced within 0.001: "
              f"{within} ({100.0 * within / len(repeats):.1f} %), "
              f"max |Δ| {max(repeats):.3f}, mean |Δ| {sum(repeats) / len(repeats):.4f}")


if __name__ == "__main__":
    main()
