"""Dry-run of the RQI direction flip (x -> 6 - x). READ-ONLY.

Prints, per stored RQI value, the distribution before and after the flip
using the exact SQL expressions of backend/alembic/versions/0006_rqi_flip_direction.py,
checks the invariants (row/NULL counts, bad-road counts, probabilities
untouched) and validates every UPDATE with EXPLAIN (planned, never executed).
The whole session runs in a READ ONLY transaction and is rolled back.

Usage (from backend/):
    ../.venv/bin/python scripts/rqi_flip_dry_run.py            # DATABASE_URL
    ../.venv/bin/python scripts/rqi_flip_dry_run.py --url postgresql://...
Exit code: 0 = all invariants hold, 1 = a check failed.
"""
import argparse
import importlib.util
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa  # noqa: E402

warnings.filterwarnings("ignore", message="Did not recognize type")  # PostGIS columns

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(BACKEND, "alembic", "versions", "0006_rqi_flip_direction.py")
BAD_FROM_OLD = 3  # bad road today: value >= 3; after the flip: value <= 6 - 3
TOLERANCE = 1e-9  # accepted round-trip deviation for continuous double columns


def load_migration():
    spec = importlib.util.spec_from_file_location("rqi_flip_direction", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dist(conn, table, expr, where, digits=None):
    """Value counts; exact for discrete columns, binned (display only) for continuous."""
    v = f"({expr})" if digits is None else f"round(({expr})::numeric, {digits})"
    rows = conn.execute(sa.text(
        f"SELECT {v} AS v, count(*) FROM {table} WHERE {where} GROUP BY 1 ORDER BY 1")).fetchall()
    return {float(v): int(n) for v, n in rows}


def _fmt(d):
    return "  ".join(f"{v:g}:{n}" for v, n in d.items()) or "(none)"


def check_target(conn, M, table, value_expr, where, label, decimals=None):
    """Before/after report for one stored value; returns list of failures.

    decimals=None: a float column, mirrored as M - x in double precision. The
    round trip is bit-exact for the level / half-step values we store, and
    within ~1 ulp (1e-15) for arbitrary continuous doubles such as
    road_segments.score: accepted up to TOLERANCE, reported either way.
    decimals=k: a JSON value mirrored through numeric and round(.., k), which
    is lossless iff no value has more than k decimals.
    """
    fails = []
    after_expr = f"({M.MIRROR} - {value_expr})"
    q = conn.execute(sa.text(
        f"SELECT count(*), count(*) FILTER (WHERE {where}), "
        f"min({value_expr}), max({value_expr}), avg({value_expr}), "
        f"count(*) FILTER (WHERE {where} AND {value_expr} >= {BAD_FROM_OLD}), "
        f"min({after_expr}), max({after_expr}), avg({after_expr}), "
        f"count(*) FILTER (WHERE {where} AND {after_expr} <= {M.MIRROR - BAD_FROM_OLD}) "
        f"FROM {table}")).one()
    total, nonnull, bmin, bmax, bavg, bbad, amin, amax, aavg, abad = q
    digits = None if decimals is None else 1
    before = _dist(conn, table, value_expr, where, digits)
    after = _dist(conn, table, after_expr, where, digits)
    if decimals is None:
        inexact, max_dev = conn.execute(sa.text(
            f"SELECT count(*) FILTER (WHERE ({M.MIRROR} - {after_expr}) <> {value_expr}), "
            f"coalesce(max(abs(({M.MIRROR} - {after_expr}) - {value_expr})), 0) "
            f"FROM {table} WHERE {where}")).one()
        lossy = 0 if float(max_dev) <= TOLERANCE else inexact
    else:
        inexact = lossy = conn.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE {where} AND "
            f"{value_expr} <> round({value_expr}, {decimals})")).scalar()
        max_dev = 0
    print(f"\n== {label}  ({table}: {total} rows, {nonnull} with a value -> {nonnull} updated)")
    if nonnull:
        print(f"   before: min {float(bmin):g}  max {float(bmax):g}  mean {float(bavg):.3f}  "
              f"bad (>= {BAD_FROM_OLD}): {bbad}")
        print(f"   after : min {float(amin):g}  max {float(amax):g}  mean {float(aavg):.3f}  "
              f"bad (<= {M.MIRROR - BAD_FROM_OLD}): {abad}")
    binned = "" if decimals is None else " (0.1 bins)"
    print(f"   before dist{binned}: {_fmt(before)}")
    print(f"   after  dist{binned}: {_fmt(after)}")
    if lossy:
        verdict = f"NO, {lossy} rows"
    elif inexact:
        verdict = (f"yes within {TOLERANCE:g} ({inexact} continuous values differ by "
                   f"<= {float(max_dev):.1e}, float rounding)")
    else:
        verdict = "yes, exactly"
    print(f"   reversible (downgrade restores every value): {verdict}")
    if bbad != abad:
        fails.append(f"{label}: bad-road count changes {bbad} -> {abad}")
    if lossy:
        fails.append(f"{label}: {lossy} values would not round-trip exactly")
    # exact value-count mirror: only meaningful when every value round-trips exactly
    if decimals is None and not inexact and {M.MIRROR - v: n for v, n in before.items()} != after:
        fails.append(f"{label}: after-distribution is not the mirror of before")
    if nonnull and abs((float(bavg) + float(aavg)) - M.MIRROR) > 1e-6:
        fails.append(f"{label}: mean before + after != {M.MIRROR}")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", help="database URL (default: settings.DATABASE_URL)")
    args = ap.parse_args(argv)
    if args.url:
        url = args.url
    else:
        from app.core.config import settings
        url = settings.DATABASE_URL
    M = load_migration()
    engine = sa.create_engine(url)
    fails = []
    print(f"RQI flip dry-run (read-only) on {url.split('@')[-1]}")
    print(f"migration: {os.path.relpath(MIGRATION, BACKEND)} (revision {M.revision}, "
          f"revises {M.down_revision}); mapping x -> {M.MIRROR} - x")
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        insp = sa.inspect(conn)
        tables = set(insp.get_table_names())
        def present(t):
            return t[0] in tables and t[1] in {c["name"] for c in insp.get_columns(t[0])}
        targets = list(M.COLUMN_TARGETS) + [t for t in M.OPTIONAL_COLUMN_TARGETS if present(t)]
        skipped = [t for t in M.OPTIONAL_COLUMN_TARGETS if not present(t)]
        for table, column in targets:
            fails += check_target(conn, M, table, column, f"{column} IS NOT NULL",
                                  f"{table}.{column}")
        for table, column, key, dec in M.JSON_TARGETS:
            expr = M.json_value_expr(column, key)
            fails += check_target(conn, M, table, expr, f"{column}->>'{key}' IS NOT NULL",
                                  f"{table}.{column}.{key}", decimals=dec)
        if skipped:
            print("\n(skipped, not in this DB: " + ", ".join(f"{t}.{c}" for t, c in skipped) + ")")

        # Probabilities are not touched: show they exist and stay as they are.
        n_pbad = conn.execute(sa.text(
            "SELECT count(*) FROM street_view_images "
            "WHERE analysis_metadata->>'dino_p_bad' IS NOT NULL")).scalar()
        print(f"\n== street_view_images.analysis_metadata.dino_p_bad: {n_pbad} values, unchanged by design")

        # Validate every UPDATE the migration would run (EXPLAIN plans, does not execute).
        print("\n== migration statements (EXPLAIN only)")
        for stmt in M.flip_statements(conn):
            try:
                conn.execute(sa.text("EXPLAIN " + stmt))
                print(f"   ok   {stmt}")
            except Exception as e:  # pragma: no cover - reported, not raised
                fails.append(f"EXPLAIN failed: {stmt}: {e}")
                print(f"   FAIL {stmt}\n        {e}")
        conn.rollback()

    print("\n" + ("ALL CHECKS PASS" if not fails else "FAILED:\n  " + "\n  ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
