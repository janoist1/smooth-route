"""Collect Street View frames along the main-road network (no route needed).

Usage (from backend/):
    ../.venv/bin/python scripts/collect_network.py --dry-run          # plan + cost, ZERO Google requests
    ../.venv/bin/python scripts/collect_network.py                    # pass 1: every 50 m
    ../.venv/bin/python scripts/collect_network.py --densify          # pass 2: 30 m on low-confidence segments
    ../.venv/bin/python scripts/collect_network.py --report           # what this job added

Options: [--bbox minLng,minLat,maxLng,maxLat] [--job NAME] [--job-cap N]
         [--max-mb MB] [--spacing M] [--offline] [--board-ticket T-34]

What it does
- Road network: ONE Overpass request for trunk / primary / secondary roads
  and their links (no motorways) in the bbox — default Budapest and its
  agglomeration — cached in data/osm/ and never fetched again.
- Plan: a point every 50 m along every road, minus stretches that already
  have frames; ~1 km cells visited one at a time, round-robin across ~5 km
  districts, so a limited budget is spread over many places.
- Per point: free metadata first (skip: no panorama, panorama already stored,
  panorama not on this road, a stored frame within 5 m), then the image
  exactly like the training frames (600×400, pitch −20, heading = road
  bearing), saved as data/images/sv_<id>_<hex>.jpg with a street_view_images
  row (pano id + capture month) like route collection does. The API key is
  never written to the DB or the log.

Safety (see app/services/sv_quota.py and sv_client.py)
- Monthly image cap GOOGLE_SV_MONTHLY_CAP (default 5000) and this run's
  --job-cap (default 4000; pass 2: 1000) are checked BEFORE every image
  request; --max-mb (default 250) caps what this job stores.
- One request at a time, GOOGLE_SV_RATE_PER_S (default 1/s) for metadata and
  images together, exponential back-off on transient errors.
- HTTP 403 / 429 or any quota / billing / key status stops the job at once.
- Resumable: every handled point is logged in data/collect/<job>.jsonl; run
  the same command again to continue. Ctrl-C stops cleanly.

After a pass (new frames are unscored): take a backup, then
    ../.venv/bin/python ../ml/frame_quality.py write --commit --backup <dump>
    HF_HUB_OFFLINE=1 ../.venv/bin/python scripts/rescore_dino.py
    ../.venv/bin/python scripts/build_segments.py
and only then --densify (it needs the segments' confidence) and --report.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Make the `app` package importable when run from backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.network_collector import (  # noqa: E402
    STOP_TROUBLE,
    ResumeLog,
    RunResult,
    run_plan,
)
from app.services.network_sampling import (  # noqa: E402
    load_sampling,
    plan_collection,
    take_budget,
)

# Budapest + agglomeration: (south, west, north, east)
DEFAULT_BOUNDS = (47.35, 18.85, 47.62, 19.35)
PASS1_JOB_CAP = 4000
PASS2_JOB_CAP = 1000
DEFAULT_MAX_MB = 250
IMAGE_KB_ESTIMATE = 45          # a 600×400 Street View JPEG


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """``minLng,minLat,maxLng,maxLat`` → (south, west, north, east)."""
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must be 'minLng,minLat,maxLng,maxLat'") from exc
    if min_lng >= max_lng or min_lat >= max_lat:
        raise argparse.ArgumentTypeError("bbox min must be below max")
    return (min_lat, min_lng, max_lat, max_lng)


def default_job_name(bounds: tuple[float, float, float, float]) -> str:
    s, w, n, e = bounds
    return f"network_{s:.2f}_{w:.2f}_{n:.2f}_{e:.2f}".replace(".", "p")


def board_note(ticket: str, message: str) -> None:
    """Best-effort progress note on the team board (never fails the job)."""
    tool = BACKEND_DIR.parent / "tools" / "board.py"
    try:
        subprocess.run([sys.executable, str(tool), "note", ticket, message],
                       check=False, capture_output=True, timeout=20)
    except Exception:
        pass


def report(db, bounds, resume: ResumeLog, images_dir: Path) -> None:
    """What this job added: images, megabytes, and the segments they are on."""
    from sqlalchemy import text

    from app.services.map_matching import LineIndex
    from app.services.route_quality import SegmentRef
    from app.services.segment_read import fetch_segments_in_boxes

    ids = resume.frame_ids
    print(f"job log: {dict(resume.counts())}")
    print(f"images saved: {len(ids)} ({resume.bytes_saved / 1e6:.1f} MB)")
    if not ids:
        return
    rows = db.execute(
        text("SELECT id, latitude, longitude, heading, dino_rqi_score FROM street_view_images "
             "WHERE id = ANY(:ids)"), {"ids": ids},
    ).fetchall()
    scored = sum(1 for r in rows if r.dino_rqi_score is not None)
    print(f"frames in DB: {len(rows)}, scored: {scored}")
    south, west, north, east = bounds
    segments = fetch_segments_in_boxes(db, [(west, south, east, north)])
    by_id = {s.id: s for s in segments}
    index = LineIndex([SegmentRef(s.id, s.path, s.rqi, s.score) for s in segments])
    touched = Counter()
    for r in rows:
        match = index.snap((r.latitude, r.longitude), r.heading)
        if match is not None:
            touched[match.line_id] += 1
    if not touched:
        print("no segments carry these frames yet — score them and run build_segments.py first")
        return
    km = sum(by_id[i].length_m for i in touched) / 1000.0
    classes, levels = Counter(), Counter()
    class_km, level_km = Counter(), Counter()
    for seg_id in touched:
        seg = by_id[seg_id]
        classes[seg.rqi] += 1
        class_km[seg.rqi] += seg.length_m / 1000.0
        levels[seg.confidence_level] += 1
        level_km[seg.confidence_level] += seg.length_m / 1000.0
    print(f"segments with new frames: {len(touched)} ({km:.1f} km)")
    print("  classes:    " + ", ".join(
        f"RQI {c}: {classes[c]} ({class_km[c]:.1f} km)" for c in sorted(classes, key=str)))
    print("  confidence: " + ", ".join(
        f"{lvl}: {levels[lvl]} ({level_km[lvl]:.1f} km)" for lvl in ("high", "medium", "low")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", type=parse_bbox, default=DEFAULT_BOUNDS,
                    help="minLng,minLat,maxLng,maxLat (default: Budapest + agglomeration)")
    ap.add_argument("--job", default=None, help="job name = resume log (default: from the bbox)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and print the cost; no Google request at all")
    ap.add_argument("--densify", action="store_true",
                    help="pass 2: dense spacing on this job's low-confidence segments")
    ap.add_argument("--report", action="store_true", help="summarise what this job added")
    ap.add_argument("--job-cap", type=int, default=None,
                    help=f"max images THIS run (default {PASS1_JOB_CAP}; --densify {PASS2_JOB_CAP})")
    ap.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB,
                    help="stop when this job has stored that many megabytes")
    ap.add_argument("--spacing", type=float, default=None,
                    help="override the sampling spacing in metres")
    ap.add_argument("--offline", action="store_true",
                    help="use the cached road network only (no Overpass request)")
    ap.add_argument("--board-ticket", default=None,
                    help="post a progress note on this board ticket every 1,000 images")
    args = ap.parse_args()

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.paths import data_path
    from app.services.frame_store import DbFrameStore, low_confidence_lines
    from app.services.osm_chains import merge_ways
    from app.services.osm_overpass import MAIN_ROAD_CLASSES, OverpassError, fetch_network
    from app.services.sv_client import StreetViewClient, rate_from_env
    from app.services.sv_quota import JobBudget, default_quota

    bounds = args.bbox
    sampling = load_sampling()
    job_name = args.job or default_job_name(bounds)
    log_path = data_path("collect", f"{job_name}{'_dense' if args.densify else ''}.jsonl")
    pass1_log = ResumeLog(data_path("collect", f"{job_name}.jsonl"))
    resume = ResumeLog(log_path)
    quota = default_quota()
    images_dir = data_path("images")

    db = SessionLocal()
    try:
        if args.report:
            both = ResumeLog(data_path("collect", f"{job_name}_dense.jsonl"))
            print(f"== pass 1 ({pass1_log.path.name})")
            report(db, bounds, pass1_log, images_dir)
            if both.status:
                print(f"== pass 2 ({both.path.name})")
                report(db, bounds, both, images_dir)
            print(quota.summary())
            return

        store = DbFrameStore(db, images_dir)
        if args.densify:
            spacing = args.spacing or sampling.dense_spacing_m
            lines = low_confidence_lines(db, bounds, pass1_log.frame_ids, sampling)
            existing = store.frames
            what = f"pass 2: {len(lines)} low-confidence segments of this job"
        else:
            spacing = args.spacing or sampling.base_spacing_m
            try:
                ways = fetch_network(data_path("osm"), bounds, MAIN_ROAD_CLASSES,
                                     allow_fetch=not args.offline)
            except OverpassError as exc:
                sys.exit(f"road network unavailable, nothing done: {exc}")
            lines = merge_ways(ways)
            # Plan against the frames that existed BEFORE this job, so the
            # plan (and its cell order) is identical on every resume.
            own = set(resume.frame_ids)
            existing = [f for f in store.frames if f.id not in own]
            what = f"pass 1: {len(ways)} ways → {len(lines)} roads"

        plan = plan_collection(lines, existing, spacing, bounds=bounds)
        todo = [(cell, [c for c in members if c.key not in resume]) for cell, members in plan]
        todo = [(cell, members) for cell, members in todo if members]
        open_points = sum(len(m) for _c, m in todo)
        job_cap = args.job_cap if args.job_cap is not None else (
            PASS2_JOB_CAP if args.densify else PASS1_JOB_CAP)
        rate = rate_from_env()

        # --max-mb is a ceiling for the JOB: pass 2 counts what pass 1 stored.
        other_pass_bytes = pass1_log.bytes_saved if args.densify else 0

        print(f"job {job_name} — {what}; spacing {spacing:g} m")
        print(f"plan: {sum(len(m) for _c, m in plan)} points in {len(plan)} cells "
              f"({sum(len(m) for _c, m in plan) * spacing / 1000:.0f} km of road without frames); "
              f"already handled {len(resume.status)}, open {open_points}")
        print(f"{quota.summary()}; this run: at most {job_cap} images, "
              f"{args.max_mb:g} MB for the job "
              f"({(resume.bytes_saved + other_pass_bytes) / 1e6:.0f} MB stored so far), "
              f"{rate:g} request/s")

        if args.dry_run:
            budget = max(0, min(job_cap, quota.remaining()))
            fit = take_budget(todo, budget)
            points = sum(len(m) for _c, m in fit)
            print("DRY RUN — no Google request was made.")
            print(f"  with {budget} images this run reaches {len(fit)} cells in "
                  f"{len({(c[0] // 5, c[1] // 5) for c, _m in fit})} districts: "
                  f"up to {points} images (one per point at most; fewer where there is "
                  f"no panorama or it is a duplicate)")
            print(f"  ≈ {points * spacing / 1000:.0f} km of road, "
                  f"≈ {points * IMAGE_KB_ESTIMATE / 1000:.0f} MB, "
                  f"≈ {points * 2 / rate / 3600:.1f} h at {rate:g} request/s "
                  f"(metadata + image per point)")
            return

        if not todo:
            print("nothing left to do for this job")
            return
        if not settings.GOOGLE_MAPS_API_KEY:
            sys.exit("GOOGLE_MAPS_API_KEY not set (env or repo-root .env).")
        images_dir.mkdir(parents=True, exist_ok=True)
        client = StreetViewClient(settings.GOOGLE_MAPS_API_KEY, quota)

        def progress(result: RunResult, log: ResumeLog) -> None:
            message = (f"{job_name}{' pass 2' if args.densify else ''}: {len(log.frame_ids)} images "
                       f"saved ({log.bytes_saved / 1e6:.0f} MB), {result.cells_done} cells done; "
                       f"{quota.summary()}")
            print(message, flush=True)
            if args.board_ticket:
                board_note(args.board_ticket, message)

        result = run_plan(
            todo, client=client, store=store, lines=lines, resume=resume,
            job=JobBudget(job_cap), radius_m=spacing / 2.0,
            max_bytes=max(0, int(args.max_mb * 1e6) - other_pass_bytes),
            on_progress=progress,
        )
    finally:
        db.close()

    summary = (f"{job_name}{' pass 2' if args.densify else ''} — {result.stop}"
               f"{': ' + result.detail if result.detail else ''}. This run: {dict(result.counts)}; "
               f"job total {len(resume.frame_ids)} images, {resume.bytes_saved / 1e6:.1f} MB, "
               f"≈ {len(resume.frame_ids) * spacing / 1000:.0f} km. {quota.summary()}")
    print(summary)
    if args.board_ticket:
        board_note(args.board_ticket, summary)
    if result.stop == STOP_TROUBLE:
        sys.exit(2)


if __name__ == "__main__":
    main()
