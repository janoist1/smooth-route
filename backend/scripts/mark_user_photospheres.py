"""Mark stored user-contributed photospheres as unusable frames (one-off, T-42).

User photospheres (pano ids "CAoS…", copyright = a person, not "© … Google")
are not road-level Street View car imagery; they pollute scoring. New ones are
skipped by the collector (network_collector USER_PANO); this script flags the
ones already stored:

    analysis_metadata.frame_quality.usable = false
    analysis_metadata.frame_quality.reasons += ["user_photosphere"]

Other frame_quality fields are kept. Consumers already skip usable == false.

Usage (from backend/):
    ../.venv/bin/python scripts/mark_user_photospheres.py --dry-run
    ../.venv/bin/python scripts/mark_user_photospheres.py [--verify]

--verify  confirm each candidate with the FREE metadata call (copyright must
          not name Google); without it the "CAoS" id pattern decides (it
          matched the copyright on every sampled frame).
Before writing, the changed rows' old analysis_metadata go to
data/backups/user_photospheres_<UTC>.json (exact restore: write them back).
Idempotent: frames already carrying the reason are left alone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sv_client import USER_PANO_ID_PREFIX, is_google_pano  # noqa: E402

REASON = "user_photosphere"


def mark(meta: dict | None) -> dict:
    """analysis_metadata with frame_quality flagged unusable for REASON (new dict)."""
    meta = dict(meta or {})
    fq = dict(meta.get("frame_quality") or {})
    reasons = list(fq.get("reasons") or [])
    if REASON not in reasons:
        reasons.append(REASON)
    fq.update(usable=False, reasons=reasons)
    meta["frame_quality"] = fq
    return meta


def already_marked(meta: dict | None) -> bool:
    fq = (meta or {}).get("frame_quality") or {}
    return fq.get("usable") is False and REASON in (fq.get("reasons") or [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="confirm each candidate's copyright with a free metadata call")
    args = ap.parse_args()

    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.core.paths import data_path

    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT id, pano_id, analysis_metadata FROM street_view_images "
            "WHERE pano_id LIKE :p ORDER BY id"), {"p": USER_PANO_ID_PREFIX + "%"}).all()
        todo = [(i, p, m if isinstance(m, dict) else json.loads(m or "{}"))
                for i, p, m in rows]
        todo = [(i, p, m) for i, p, m in todo if not already_marked(m)]
        print(f"{len(rows)} frames with a user-photosphere id; {len(todo)} not marked yet")
        if args.verify and todo:
            from app.services.sv_client import default_client

            client, kept = default_client(), []
            for i, p, m in todo:
                meta = client.metadata(pano_id=p)
                if meta and not is_google_pano(meta):
                    kept.append((i, p, m))
                else:
                    print(f"  keep frame {i}: copyright {meta and meta.get('copyright')!r}")
            todo = kept
            print(f"{len(todo)} confirmed by copyright")
        if args.dry_run or not todo:
            print("dry run: nothing written" if args.dry_run else "nothing to do")
            return 0

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = data_path("backups", f"user_photospheres_{stamp}.json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps({str(i): m for i, _, m in todo}, ensure_ascii=False))
        for i, _, m in todo:
            db.execute(text("UPDATE street_view_images SET analysis_metadata = CAST(:m AS json) "
                            "WHERE id = :i"), {"m": json.dumps(mark(m)), "i": i})
        db.commit()
        print(f"marked {len(todo)} frames unusable ({REASON}); old values in {backup}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
