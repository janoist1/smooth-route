"""Read-only real-data counts for the configurable weak-spots label queue.

From backend/: .venv-python scripts/weak_spots_report.py
Uses the queue's local images, score-cache fallback, live cut-points, spatial
exclusions and heading-aware segment links. No network or model inference.
"""
from __future__ import annotations

import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.services import label_queue as lq  # noqa: E402
from app.services import label_queue_store as store  # noqa: E402
from app.services import weak_spots as weak  # noqa: E402


def rule_counts(frames, labelled, cuts, config):
    """Per-rule matches and full thinned capacity; pools may overlap."""
    eligible = lq.eligible_frames(frames, labelled)
    pools = weak.rule_pools(eligible, labelled, cuts, config)
    total_share = sum(rule.share for rule in config.rules)
    return [
        (rule.key, rule.share / total_share, len(pools[rule.key]),
         len(weak.pick(eligible, labelled, len(eligible), cuts,
                       replace(config, rules=(replace(rule, share=1),)))))
        for rule in config.rules
    ]


def main() -> None:
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        frames, labelled, _ = store.load_inputs(db)
        cuts = store.cut_points()
        frames = store.weak_spot_inputs(db, frames, cuts)
        config = weak.load_config()
        print(f"Config: {weak.CONFIG_PATH}; thinning: {config.thin_radius_m:g} m")
        print("rule                     share     matches     spaced")
        for key, share, matches, spaced in rule_counts(frames, labelled, cuts, config):
            print(f"{key:24} {share:6.1%} {matches:11d} {spaced:10d}")
        print("Matches include shared exclusions; spaced adds thinning against labels.")
        print("Pools may overlap; counts are independent, not additive. Zero share disables a rule.")


if __name__ == "__main__":
    main()
