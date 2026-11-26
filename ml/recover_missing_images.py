#!/usr/bin/env python3
"""
Recover labelled training images that are referenced in ml/labels.csv but
missing from data/images/.

The missing files use the old `sv_{svi_id}_{uuid}.jpg` naming; their
street_view_images rows still exist, so we re-fetch the exact camera setup
(lat/lon/heading, pitch -20, 600x400) from the Street View Static API and save
under the ORIGINAL filename the label references.

Guard against label drift: the labels were made in January 2026. For every
point we first hit the free metadata endpoint; if the pano at that location
was captured AFTER the labelling date, the road may have changed since it was
scored, so we skip it (reported at the end).

Every request goes through the backend's shared Street View client
(backend/app/services/sv_client.py): images are booked on the monthly quota
counter and this run's cap BEFORE they are requested, traffic is paced at
~1 request/s, and a quota / billing signal stops the run.

Usage:  .venv/bin/python ml/recover_missing_images.py [--limit N] [--dry-run]
"""
import argparse
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "data", "images")
LABELS = os.path.join(ROOT, "ml", "labels.csv")

sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.sv_client import (  # noqa: E402
    StreetViewClient,
    StreetViewError,
    StreetViewFatal,
)
from app.services.sv_quota import (  # noqa: E402
    DEFAULT_JOB_CAP,
    JobBudget,
    QuotaExceeded,
    cap_from_env,
    default_quota,
)

# Labels were created 2026-01-02 .. 2026-01-17; any pano captured in or after
# Feb 2026 cannot be what the labeller saw.
LABEL_CUTOFF = "2026-02"


def api_key():
    # .env style: GOOGLE_MAPS_API_KEY=...
    env_path = os.path.join(ROOT, ".env")
    if os.environ.get("GOOGLE_MAPS_API_KEY"):
        return os.environ["GOOGLE_MAPS_API_KEY"]
    with open(env_path) as f:
        for line in f:
            m = re.match(r"^GOOGLE_MAPS_API_KEY=(.+)$", line.strip())
            if m:
                return m.group(1)
    sys.exit("GOOGLE_MAPS_API_KEY not found in env or .env")


def load_targets():
    """Rows from the DB export produced by the session (svi join)."""
    path = os.path.join(ROOT, "ml", "missing_labelled_mapped.csv")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    todo = [r for r in rows if not os.path.exists(os.path.join(IMAGES, r["image_filename"]))]
    return todo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = api_key()
    todo = load_targets()
    if args.limit:
        todo = todo[: args.limit]
    print(f"Missing labelled images to recover: {len(todo)}")

    os.makedirs(IMAGES, exist_ok=True)
    ok, skipped_new_pano, no_pano, failed = 0, [], [], []
    client = StreetViewClient(key, default_quota())
    budget = JobBudget(cap_from_env("GOOGLE_SV_JOB_CAP", DEFAULT_JOB_CAP))
    print(client.quota.summary(), f"| this run: at most {budget.cap} images")

    for i, r in enumerate(todo, 1):
        lat, lng = float(r["latitude"]), float(r["longitude"])
        heading, pitch = float(r["heading"]), float(r["pitch"])
        fname = r["image_filename"]

        try:
            meta = client.metadata(lat, lng, radius=15)
        except StreetViewFatal as stop:
            print(f"STOPPED: {stop}")
            break
        except StreetViewError as e:
            failed.append((fname, f"meta error: {e}"))
            continue

        if meta is None:
            no_pano.append((fname, "no panorama"))
            continue

        pano_date = meta.get("date") or ""  # e.g. "2023-06"
        if pano_date and pano_date >= LABEL_CUTOFF:
            skipped_new_pano.append((fname, pano_date))
            continue

        if args.dry_run:
            ok += 1
            continue

        try:
            body = client.image(lat=lat, lng=lng, heading=heading, pitch=pitch, job=budget)
        except (QuotaExceeded, StreetViewFatal) as stop:
            print(f"STOPPED: {stop}")
            break
        except StreetViewError as e:
            failed.append((fname, str(e)))
        else:
            with open(os.path.join(IMAGES, fname), "wb") as f:
                f.write(body)
            ok += 1

        if i % 25 == 0:
            print(f"  {i}/{len(todo)}  ok={ok} newer_pano={len(skipped_new_pano)} "
                  f"no_pano={len(no_pano)} failed={len(failed)}")

    print(f"\nDone. downloaded={ok}  skipped(newer pano)={len(skipped_new_pano)}  "
          f"no_pano={len(no_pano)}  failed={len(failed)}")
    if skipped_new_pano[:10]:
        print("newer-pano examples:", skipped_new_pano[:10])
    if failed[:10]:
        print("failures:", failed[:10])


if __name__ == "__main__":
    main()
