#!/usr/bin/env python3
"""How consistent is the owner with themself? -> the label-noise ceiling.

Frames re-rated blind on the quick-rate screen ("Újraellenőrzés" strategy)
keep their old values in training_data.meta_data.relabel_history. This script
compares each frame's ORIGINAL label with its latest re-check and reports the
share rated the same / within one level, per original level, plus the
quadratic-weighted kappa between the two passes. A model cannot be expected to
agree with the labels more than the labeller agrees with themself, so this QWK
is the practical ceiling for the spatial-CV QWK (champion 0.774).

Values are read through the canonical scale (ml/rqi_scale.py), with the
direction each value was written in, so a scale flip does not change results.

Usage:  .venv/bin/python ml/label_consistency.py   (needs the DB: docker compose up -d db)
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rqi_scale import SCALE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5433/smooth_route")

# The same statistics the quick-rate screen shows (one implementation).
_spec = importlib.util.spec_from_file_location(
    "_label_queue", os.path.join(ROOT, "backend", "app", "services", "label_queue.py"))
_lq = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _lq
_spec.loader.exec_module(_lq)


def load_histories():
    import psycopg2

    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT meta_data->'relabel_history' FROM training_data "
                    "WHERE (meta_data::jsonb) ? 'relabel_history'")
        return [h for (h,) in cur.fetchall() if h]


def qwk(histories, reason):
    """QWK original vs latest, on integer levels in severity orientation."""
    from sklearn.metrics import cohen_kappa_score

    a, b = [], []
    for hist in histories:
        if hist[0].get("reason") != reason:
            continue
        old = SCALE.convert(float(hist[0]["old"]), hist[0].get("direction", SCALE.direction))
        new = SCALE.convert(float(hist[-1]["new"]), hist[-1].get("direction", SCALE.direction))
        a.append(int(SCALE.to_severity(SCALE.nearest(old))))
        b.append(int(SCALE.to_severity(SCALE.nearest(new))))
    if len(set(a) | set(b)) < 2:
        return None
    return cohen_kappa_score(a, b, weights="quadratic")


def report(histories, reason, title):
    st = _lq.consistency_stats(histories, SCALE, reason=reason)
    print(f"\n== {title} ==")
    if not st["n"]:
        print("   no re-checked frames yet")
        return
    print(f"   n={st['n']}   same: {st['same']:.1%}   within one: {st['within_one']:.1%}")
    k = qwk(histories, reason)
    if k is not None:
        print(f"   QWK original vs re-check: {k:.3f}")
    print(f"   {'original level':<22}{'n':>5}{'same':>8}{'±1':>8}")
    for lv, row in st["per_level"].items():
        name = f"{lv} {SCALE.level(lv).label_hu}"
        same = "-" if row["same"] is None else f"{row['same']:.0%}"
        near = "-" if row["within_one"] is None else f"{row['within_one']:.0%}"
        print(f"   {name:<22}{row['n']:>5}{same:>8}{near:>8}")


def main():
    histories = load_histories()
    if not histories:
        print("No re-checked frames yet (quick-rate screen, strategy Újraellenőrzés).")
        return 0
    report(histories, "recheck_sample",
           "Random control sample -> the label-noise ceiling (use THIS number)")
    report(histories, "recheck_suspicious",
           "Suspicious frames (label_audit.csv) -> how many old labels were wrong; biased, not a ceiling")
    print("\nShares are rough until ~50+ frames per level.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
