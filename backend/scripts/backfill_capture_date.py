"""Backfill street_view_images.capture_date (and pano_id) from the free
Street View Metadata API.

Usage (from backend/):
    ../.venv/bin/python scripts/backfill_capture_date.py [--limit N] [--qps 10]
        [--workers 4] [--chunk 200] [--dry-run]

- Only rows with capture_date IS NULL are touched → safe to re-run / resume;
  results are committed per chunk, so an interrupt loses at most one chunk.
- Metadata requests are free (no Street View Static quota), but the script
  still rate-limits (`--qps`) and retries OVER_QUERY_LIMIT / network errors.
- Rows WITH a pano_id are looked up by pano id → exact date of our image.
- Rows WITHOUT one are looked up by location → the date is only stored when
  the live panorama predates our download month (see
  app.services.capture_date.backfill_decision); then pano_id is filled too.
  Otherwise the row stays NULL ("newer pano": Google replaced the imagery
  since we fetched it, so its date would not describe our image). Those rows
  are re-queried on every run — cheap, and harmless.

Needs GOOGLE_MAPS_API_KEY (env or the repo-root .env) and the local DB.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

# Make the `app` package importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from app.services.capture_date import (  # noqa: E402
    ACCEPT,
    backfill_decision,
)

META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
# Statuses worth retrying (transient); everything else is final for this run.
RETRY_STATUSES = {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR", "HTTP_ERROR", "EXCEPTION"}
# Quota / billing / key problems: stop the run (commit what is done, report
# the counts) instead of hammering the API. OVER_QUERY_LIMIT lands here only
# after its retries were exhausted.
FATAL_STATUSES = {"OVER_QUERY_LIMIT", "REQUEST_DENIED", "HTTP_403"}
# Points were stored at the panorama's exact (snapped) coordinates, so a tight
# radius picks that spot's live pano and not a neighbouring one.
LOCATION_RADIUS_M = 10


class RateLimiter:
    """Thread-safe fixed-interval limiter: at most `qps` acquisitions/second."""

    def __init__(self, qps: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if qps <= 0:
            raise ValueError("qps must be > 0")
        self.interval = 1.0 / qps
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = clock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self.interval
        delay = slot - now
        if delay > 0:
            self._sleep(delay)


def fetch_metadata(http, key: str, limiter: RateLimiter, *, pano_id: Optional[str] = None,
                   lat: Optional[float] = None, lng: Optional[float] = None,
                   retries: int = 3) -> tuple[str, Optional[dict]]:
    """One metadata lookup with rate limiting + retry. Returns (status, json)."""
    params = {"key": key}
    if pano_id:
        params["pano"] = pano_id
    else:
        params["location"] = f"{lat},{lng}"
        params["radius"] = LOCATION_RADIUS_M

    status, data = "EXCEPTION", None
    for attempt in range(retries + 1):
        limiter.wait()
        try:
            resp = http.get(META_URL, params=params, timeout=10)
            if resp.status_code == 403:
                status, data = "HTTP_403", None
            elif resp.status_code != 200:
                status, data = "HTTP_ERROR", None
            else:
                data = resp.json()
                status = data.get("status", "UNKNOWN_ERROR")
        except Exception:  # network hiccup → retry
            status, data = "EXCEPTION", None
        if status not in RETRY_STATUSES:
            break
        time.sleep(min(30, 2 ** attempt))
    return status, data


def resolve_row(row, lookup) -> tuple[str, Optional[object], Optional[str]]:
    """Decide one row. `row` = (id, lat, lng, pano_id, created_at).

    Returns (outcome, capture_date, pano_id_to_fill). Outcome is an API error
    status (row left for a later run) or a backfill_decision outcome.
    """
    _id, lat, lng, pano_id, created_at = row
    if pano_id:
        status, data = lookup(pano_id=pano_id)
    else:
        status, data = lookup(lat=lat, lng=lng)
    if status == "ZERO_RESULTS" or status == "NOT_FOUND":
        return "no_pano", None, None
    if status != "OK":
        return f"error:{status}", None, None
    outcome, capture = backfill_decision(
        data, by_pano_id=bool(pano_id), image_fetched_at=created_at
    )
    fill_pano = data.get("pano_id") if (outcome == ACCEPT and not pano_id) else None
    return outcome, capture, fill_pano


def quota_errors(counts) -> dict:
    """The quota/billing error counts in an outcome Counter (empty = fine)."""
    return {k: v for k, v in counts.items()
            if k.startswith("error:") and k[len("error:"):] in FATAL_STATUSES}


def load_api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    from app.core.config import settings

    if settings.GOOGLE_MAPS_API_KEY:
        return settings.GOOGLE_MAPS_API_KEY
    sys.exit("GOOGLE_MAPS_API_KEY not set (env or repo-root .env).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="max rows this run (0 = all)")
    ap.add_argument("--qps", type=float, default=10.0, help="max metadata requests/second")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--chunk", type=int, default=200, help="rows per commit")
    ap.add_argument("--dry-run", action="store_true", help="query, but write nothing")
    args = ap.parse_args()

    from app.core.database import SessionLocal
    from app.models.models import StreetViewImage as SVI

    key = load_api_key()
    limiter = RateLimiter(args.qps)
    http = requests.Session()

    def lookup(**kw):
        return fetch_metadata(http, key, limiter, **kw)

    db = SessionLocal()
    try:
        q = (
            db.query(SVI.id, SVI.latitude, SVI.longitude, SVI.pano_id, SVI.created_at)
            .filter(SVI.capture_date.is_(None))
            .order_by(SVI.id)
        )
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        print(f"rows with unknown capture_date: {len(rows)}"
              f"{' (dry run)' if args.dry_run else ''}")

        counts: Counter = Counter()
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for start in range(0, len(rows), args.chunk):
                chunk = rows[start : start + args.chunk]
                results = list(pool.map(lambda r: resolve_row(r, lookup), chunk))
                for row, (outcome, capture, fill_pano) in zip(chunk, results):
                    counts[outcome] += 1
                    if outcome != ACCEPT or args.dry_run:
                        continue
                    values = {"capture_date": capture}
                    if fill_pano:
                        values["pano_id"] = fill_pano
                    db.query(SVI).filter(
                        SVI.id == row[0], SVI.capture_date.is_(None)
                    ).update(values, synchronize_session=False)
                if not args.dry_run:
                    db.commit()
                done = start + len(chunk)
                rate = done / max(1e-6, time.monotonic() - started)
                print(f"  {done}/{len(rows)}  {rate:.1f} rows/s  {dict(counts)}", flush=True)
                fatal = quota_errors(counts)
                if fatal:
                    print(f"STOPPED on quota/billing error {fatal} after {done} rows "
                          f"(committed so far; re-run resumes).", flush=True)
                    break
    finally:
        db.close()

    print("summary:", dict(counts))
    if quota_errors(counts):
        sys.exit(2)


if __name__ == "__main__":
    main()
