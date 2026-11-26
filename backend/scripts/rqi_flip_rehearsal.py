"""Rehearse the pending RQI flip migration on a THROWAWAY copy of the data.

Never writes to the source database. Steps:
  1. start an ephemeral PostGIS container (docker run --rm, no volume);
  2. build the schema up to the migration's parent revision (alembic);
  3. copy training_data + street_view_images from the source via pg_dump
     (a read-only snapshot, run inside the source's docker container);
  4. check the guard (upgrade must refuse while the scale is still 1 = best);
  5. upgrade with a mirrored scale -> every RQI value is 6 - x, nothing else
     changed, P(bad) untouched, and the ML export of the flipped DB equals
     today's export (so ml/labels.csv, the caches and the gate are identical);
  6. downgrade -> every row equals the original again;
  7. remove the container.

Usage (from backend/; needs docker and the local postgis image):
    ../.venv/bin/python scripts/rqi_flip_rehearsal.py
    [--source-container smooth-route-db-1] [--source-db smooth_route] [--keep]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402

from app.core import rqi_scale as core  # noqa: E402
from app.core.migrations import alembic_config  # noqa: E402

warnings.filterwarnings("ignore", message="Did not recognize type")

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING = os.path.join(BACKEND, "alembic", "pending", "rqi_flip_direction.py")
IMAGE = "postgis/postgis:16-3.4"
NAME = "rqi-flip-rehearsal"
PORT = 55433
PW = "rehearsal"
URL = f"postgresql://postgres:{PW}@127.0.0.1:{PORT}/smooth_route"


def sh(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw)


def start_container():
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    sh("docker", "run", "--rm", "-d", "--name", NAME, "-e", f"POSTGRES_PASSWORD={PW}",
       "-e", "POSTGRES_DB=smooth_route", "-p", f"127.0.0.1:{PORT}:5432", IMAGE)
    # The postgis image runs its init scripts, then restarts the server once:
    # wait until a real connection succeeds twice, a few seconds apart.
    engine = sa.create_engine(URL, pool_pre_ping=True)
    streak = 0
    for _ in range(120):
        try:
            with engine.connect() as c:
                c.execute(sa.text("SELECT postgis_version()"))
            streak += 1
            if streak >= 2:
                engine.dispose()
                return
            time.sleep(3)
            continue
        except Exception:
            streak = 0
        engine.dispose()
        time.sleep(1)
    raise RuntimeError("rehearsal container did not become ready")


def alembic_cfg(script_dir):
    cfg = alembic_config()
    cfg.set_main_option("script_location", script_dir)
    cfg.set_main_option("sqlalchemy.url", URL)
    return cfg


def script_dir_with_pending(tmp, M):
    """Copy of backend/alembic with the pending flip placed in versions/."""
    dst = os.path.join(tmp, "alembic")
    shutil.copytree(os.path.join(BACKEND, "alembic"), dst,
                    ignore=shutil.ignore_patterns("__pycache__", "pending"))
    shutil.copy(PENDING, os.path.join(dst, "versions", "rqi_flip_direction.py"))
    return dst


TABLES = ("training_data", "street_view_images")


def align_columns(source_container, source_db):
    """Add columns the source has but the fresh schema lacks (legacy leftovers
    such as training_data.manual_dino_rqi), so pg_dump's COPY loads as-is."""
    def cols(container, db):
        out = sh("docker", "exec", container, "psql", "-At", "-U", "postgres", "-d", db, "-c",
                 "SELECT table_name, column_name, data_type FROM information_schema.columns "
                 "WHERE table_schema='public' AND table_name IN ('training_data','street_view_images')")
        return {(t, c): ty for t, c, ty in (ln.split("|") for ln in out.stdout.splitlines()
                                             if ln.count("|") == 2)}
    src, dst = cols(source_container, source_db), cols(NAME, "smooth_route")
    for (t, c), ty in sorted(src.items()):
        if (t, c) not in dst:
            sh("docker", "exec", NAME, "psql", "-U", "postgres", "-d", "smooth_route", "-c",
               f'ALTER TABLE {t} ADD COLUMN "{c}" {ty}')
            print(f"  (added legacy column {t}.{c} {ty} to the scratch schema)")


def copy_data(source_container, source_db):
    align_columns(source_container, source_db)
    dump = subprocess.run(
        ["docker", "exec", source_container, "pg_dump", "-U", "postgres", "-d", source_db,
         "--data-only", "--no-owner", "-t", "training_data", "-t", "street_view_images"],
        check=True, capture_output=True)
    subprocess.run(["docker", "exec", "-i", NAME, "psql", "-q", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", "smooth_route"],
                   input=dump.stdout, check=True, capture_output=True)


TARGET_SVI = ("rqi_score", "dino_rqi_score")


def snapshot(conn):
    """Targets + the rest of every row (as jsonb) for exact comparison."""
    td = {r.id: (r.manual_rqi, r.rest, r.legacy) for r in conn.execute(sa.text(
        "SELECT id, manual_rqi, to_jsonb(t) - 'manual_rqi' - 'manual_dino_rqi' AS rest, "
        "(to_jsonb(t)->>'manual_dino_rqi')::float AS legacy FROM training_data t"))}
    svi = {r.id: (r.rqi_score, r.dino_rqi_score,
                  r.dino_score, r.meta_rest, r.rest) for r in conn.execute(sa.text(
        "SELECT id, rqi_score, dino_rqi_score, "
        "(analysis_metadata->>'dino_score')::numeric AS dino_score, "
        "analysis_metadata::jsonb - 'dino_score' AS meta_rest, "
        "to_jsonb(s) - 'rqi_score' - 'dino_rqi_score' - 'analysis_metadata' AS rest "
        "FROM street_view_images s"))}
    return td, svi


def export_rows(conn, expr):
    return conn.execute(sa.text(
        f"SELECT image_filename, {expr} AS manual_rqi, tags, comment FROM training_data "
        f"WHERE manual_rqi IS NOT NULL ORDER BY image_filename")).fetchall()


def mirror(x):
    if x is None:
        return None
    return (Decimal(6) - x) if isinstance(x, Decimal) else 6 - x


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source-container", default="smooth-route-db-1")
    ap.add_argument("--source-db", default="smooth_route")
    ap.add_argument("--keep", action="store_true", help="leave the container running")
    args = ap.parse_args(argv)

    import importlib.util
    spec = importlib.util.spec_from_file_location("rqi_flip_direction", PENDING)
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)

    checks = []

    def check(ok, what):
        checks.append((bool(ok), what))
        print(f"  [{'PASS' if ok else 'FAIL'}] {what}")

    tmp = tempfile.mkdtemp(prefix="rqi-flip-")
    print(f"starting throwaway {IMAGE} as {NAME} on :{PORT} ...")
    start_container()
    try:
        cfg = alembic_cfg(script_dir_with_pending(tmp, M))
        command.upgrade(cfg, M.down_revision)
        print(f"schema at {M.down_revision}; copying data from {args.source_container}/"
              f"{args.source_db} (pg_dump, read-only) ...")
        copy_data(args.source_container, args.source_db)
        engine = sa.create_engine(URL)
        with engine.connect() as c:
            td0, svi0 = snapshot(c)
            export0 = export_rows(c, "manual_rqi")
        print(f"copied {len(td0)} training_data + {len(svi0)} street_view_images rows")

        print("\n1) guard: upgrade with the scale still 1 = best must refuse")
        try:
            command.upgrade(cfg, M.revision)
            check(False, "upgrade refused while direction=lower_is_better")
        except RuntimeError as e:
            check("RQI flip refused" in str(e), "upgrade refused while direction=lower_is_better")
        with engine.connect() as c:
            check(snapshot(c) == (td0, svi0), "refused upgrade left every row unchanged")

        print("\n2) upgrade with the flipped scale (5 = best)")
        orig_load = core.load_scale
        core.load_scale = lambda path=core.SCALE_PATH: core.RqiScale(orig_load(path).mirrored_data())
        try:
            command.upgrade(cfg, M.revision)
        finally:
            core.load_scale = orig_load
        with engine.connect() as c:
            td1, svi1 = snapshot(c)
            flipped_scale = core.RqiScale(core.SCALE.mirrored_data())
            ml_expr = ("manual_rqi" if flipped_scale.direction == core.SEVERITY
                       else f"({flipped_scale.min_value + flipped_scale.max_value} - manual_rqi)")
            export1 = export_rows(c, ml_expr)
        check(all(td1[k][0] == mirror(v[0]) and td1[k][1] == v[1] for k, v in td0.items()),
              "training_data.manual_rqi = 6 - x, other columns unchanged")
        check(all(td1[k][2] == mirror(v[2]) for k, v in td0.items()),
              "training_data.manual_dino_rqi (legacy, if present) = 6 - x")
        check(all(svi1[k][0] == mirror(v[0]) and svi1[k][1] == mirror(v[1]) for k, v in svi0.items()),
              "street_view_images.rqi_score / dino_rqi_score = 6 - x")
        check(all(svi1[k][2] == mirror(v[2]) for k, v in svi0.items()),
              "analysis_metadata.dino_score = 6 - x (exact, 3 decimals)")
        check(all(svi1[k][3] == v[3] and svi1[k][4] == v[4] for k, v in svi0.items()),
              "dino_p_bad and every other metadata key / column unchanged")
        check(export1 == export0,
              f"ML export of the flipped DB ({ml_expr}) == today's export "
              f"({len(export0)} rows): labels.csv, caches and gate stay identical")
        bad0 = sum(1 for v in td0.values() if v[0] is not None and v[0] >= 3)
        bad1 = sum(1 for v in td1.values() if v[0] is not None and flipped_scale.is_bad(v[0]))
        check(bad0 == bad1, f"bad-road labels unchanged ({bad0})")

        print("\n3) downgrade")
        command.downgrade(cfg, M.down_revision)
        with engine.connect() as c:
            check(snapshot(c) == (td0, svi0), "every row equals the original again")
        engine.dispose()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if args.keep:
            print(f"\ncontainer {NAME} kept running on :{PORT}")
        else:
            subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
            print(f"\ncontainer {NAME} removed")

    ok = all(c[0] for c in checks)
    print("\nREHEARSAL " + ("PASSED" if ok else "FAILED") + f" ({sum(c[0] for c in checks)}/{len(checks)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
