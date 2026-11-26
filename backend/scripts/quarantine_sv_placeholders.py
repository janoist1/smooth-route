"""Quarantine already-downloaded Street View no-imagery cards, without Google calls.

From backend/ (dry run by default):
    /Users/i/Dev/smooth-route/.venv/bin/python scripts/quarantine_sv_placeholders.py
    /Users/i/Dev/smooth-route/.venv/bin/python scripts/quarantine_sv_placeholders.py --apply

Requires the local DB and original files in DATA_DIR/images. Marks detected
cards unusable, clears their scores and capture date, and preserves the files
and other metadata. Re-running is harmless. After --apply, rebuild segments:
    /Users/i/Dev/smooth-route/.venv/bin/python scripts/build_segments.py --cached-only

This cannot authenticate the panorama of a historical road photo: looking
up an old stored id today cannot prove that a location-based download used
that id. Do not backfill those photos' dates on that assumption.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.paths import resolve_stored_image  # noqa: E402
from app.models.models import StreetViewImage  # noqa: E402
from app.services.sv_client import (  # noqa: E402
    StreetViewError,
    StreetViewPlaceholder,
    validate_image,
)

REASON = "street_view_no_imagery"


def quarantine_values(metadata):
    """Preserve other fields and append the reason once, without mutation."""
    metadata = dict(metadata or {})
    quality = dict(metadata.get("frame_quality") or {})
    reasons = list(quality.get("reasons") or [])
    if REASON not in reasons:
        reasons.append(REASON)
    quality.update(usable=False, reasons=reasons)
    metadata["frame_quality"] = quality
    return metadata


def run(db, *, apply=False, resolve=resolve_stored_image):
    counts = Counter()
    rows = db.query(StreetViewImage).filter(
        StreetViewImage.image_url.isnot(None),
        ~StreetViewImage.image_url.like("http%"),
    ).order_by(StreetViewImage.id).all()
    for row in rows:
        metadata = row.analysis_metadata or {}
        if metadata.get("imagery") or os.path.basename(row.image_url).startswith("mly_"):
            continue  # Other imagery sources are outside this repair.
        quality = metadata.get("frame_quality") or {}
        if (quality.get("usable") is False and REASON in (quality.get("reasons") or [])
                and row.rqi_score is None and row.dino_rqi_score is None
                and row.capture_date is None):
            counts["already_quarantined"] += 1
            continue
        path = resolve(row.image_url)
        if path is None:
            counts["missing_file"] += 1
            continue
        try:
            validate_image(path.read_bytes())
        except StreetViewPlaceholder:
            counts["placeholders"] += 1
            print(f"{'Quarantine' if apply else 'Would quarantine'} frame {row.id}")
            if apply:
                row.analysis_metadata = quarantine_values(metadata)
                row.rqi_score = None
                row.dino_rqi_score = None
                row.capture_date = None
        except StreetViewError:
            counts["unreadable_image"] += 1
        else:
            counts["valid_images"] += 1
    if apply:
        db.commit()
    print(f"{'Applied' if apply else 'Dry run; nothing written'}: {dict(counts)}")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run(db, apply=args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
