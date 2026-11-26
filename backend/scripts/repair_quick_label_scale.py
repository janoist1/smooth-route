#!/usr/bin/env python3
"""Repair undo backups missed by migration 0006 in the already-flipped dev DB.

Dry-run by default; --apply writes in one transaction. Load DATABASE_URL from
the repo-root .env (or --env-file); --database-url overrides the environment. The lead
should take a pg_dump before applying this one-off repair.

Only previous_rqi is converted: rqi is historical context, not the undo value.
The previous_rqi_direction/version markers make repeated runs idempotent.
Unmarked backups use their matching relabel_history direction when available;
otherwise they predate direction tracking and use the original severity scale.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import JSON, bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.rqi_scale import SCALE
from app.services.label_queue_store import quick_label_previous_rqi


def repair_metadata(metadata: dict) -> dict:
    """Copy metadata and normalize all saved undo backups, without DB access."""
    history = metadata.get("relabel_history", [])

    def repair(quick_label: dict) -> dict:
        updated = {
            **quick_label,
            "previous_rqi": quick_label_previous_rqi(quick_label, history),
            "previous_rqi_direction": SCALE.direction,
            "previous_rqi_scale_version": SCALE.version,
        }
        previous = quick_label.get("previous_quick_label")
        if isinstance(previous, dict):
            updated["previous_quick_label"] = repair(previous)
        return updated

    quick_label = metadata.get("quick_label")
    if not isinstance(quick_label, dict) or not quick_label:
        return metadata
    return {**metadata, "quick_label": repair(quick_label)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--env-file", type=Path,
                        default=Path(__file__).resolve().parents[2] / ".env")
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    load_dotenv(args.env_file)
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("set DATABASE_URL in the environment/.env or pass --database-url")

    engine = create_engine(database_url)
    count = 0
    try:
        with engine.begin() as connection:
            query = (
                "SELECT id, image_filename, meta_data FROM training_data "
                "WHERE (meta_data::jsonb) ? 'quick_label' ORDER BY id"
            )
            if args.apply:
                query += " FOR UPDATE"
            update = text("UPDATE training_data SET meta_data = :metadata WHERE id = :id").bindparams(
                bindparam("metadata", type_=JSON),
            )
            for row in connection.execute(text(query)).mappings():
                before = row["meta_data"]
                after = repair_metadata(before)
                if after == before:
                    continue
                count += 1
                print(f"id={row['id']} image={row['image_filename']}: "
                      f"{json.dumps(before['quick_label'], sort_keys=True)} -> "
                      f"{json.dumps(after['quick_label'], sort_keys=True)}")
                if args.apply:
                    connection.execute(update, {"id": row["id"], "metadata": after})
        print(f"{'Applied' if args.apply else 'Dry-run: would update'} {count} row(s).")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
