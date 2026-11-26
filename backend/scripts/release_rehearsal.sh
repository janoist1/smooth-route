#!/usr/bin/env bash
# Rehearse the Neon part of a release locally. Neon, Vercel and Google are never contacted.
#
#   cd backend && scripts/release_rehearsal.sh          # build + migrate + publish
#   scripts/release_rehearsal.sh --down                 # remove the container
#
# What it does, in a throwaway PostGIS container on 127.0.0.1:5440:
#  1. Builds the round-1 schema (Alembic 0003) in a scratch DB, takes a
#     schema-only pg_dump of it, and restores the dump as a NON-superuser owner
#     into a DB that already has PostGIS. That matches Neon: neondb_owner is not a
#     superuser, and the postgis extension already exists there.
#  2. Seeds that DB with the local points in the OLD numbering (1 = best, as
#     published in round 1), without capture_date.
#  3. Creates the read-only web role from docs/SECURITY.md (SELECT only,
#     statement_timeout 5s) BEFORE the upgrade, as the owner would on Neon. The
#     default privileges let it read road_segments, which 0005 creates later.
#     The rehearsal API on :8006 connects as that role.
#  4. Runs publish.py --dry-run, then publish.py for real, against it. Same
#     command as the release, only PUBLISH_DATABASE_URL differs.
#
# Then start the API (launch config `api-rehearsal-8006`, or the command printed
# at the end) and run: python3 scripts/smoke_public_api.py http://127.0.0.1:8006
#
# The source is the local dev DB (settings.DATABASE_URL). It is only read.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=sr-release-rehearsal
PORT=5440
IMAGE=postgis/postgis:16-3.4
PW=rehearsal                     # throwaway container, bound to 127.0.0.1 only
PY=${PY:-$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python}
SRC_CONTAINER=${SRC_CONTAINER:-smooth-route-db-1}
DUMP=$(mktemp -t sr_rehearsal_schema)
OWNER_URL="postgresql://neondb_owner:$PW@127.0.0.1:$PORT/neondb"

if [[ "${1:-}" == "--down" ]]; then
  docker rm -f "$NAME" >/dev/null && echo "removed $NAME"
  exit 0
fi

psql_su() { docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -q -U postgres "$@"; }

echo "== 0. fresh container $NAME ($IMAGE) on 127.0.0.1:$PORT"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=$PW -p 127.0.0.1:$PORT:5432 "$IMAGE" >/dev/null
# The postgis image restarts postgres once after init; wait until it stays up.
for _ in $(seq 60); do
  if docker exec "$NAME" pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1 &&
     docker exec "$NAME" psql -U postgres -h 127.0.0.1 -Atc "select 1" >/dev/null 2>&1; then
    sleep 2
    docker exec "$NAME" pg_isready -U postgres -h 127.0.0.1 >/dev/null 2>&1 && break
  fi
  sleep 1
done

echo "== 1. round-1 schema (Alembic 0003) -> schema-only dump -> restore as non-superuser"
psql_su -c "CREATE DATABASE scratch"
"$PY" - "postgresql://postgres:$PW@127.0.0.1:$PORT/scratch" <<'EOF'
import sys
from alembic import command
from app.core.migrations import alembic_config
cfg = alembic_config()
cfg.set_main_option("sqlalchemy.url", sys.argv[1])
command.upgrade(cfg, "0003")
EOF
docker exec "$NAME" pg_dump -U postgres --schema-only --no-owner --no-privileges scratch \
  > "$DUMP"
psql_su <<EOF
CREATE ROLE neondb_owner LOGIN PASSWORD '$PW' NOSUPERUSER NOCREATEROLE;
CREATE DATABASE neondb OWNER neondb_owner;
\c neondb
CREATE EXTENSION postgis;
GRANT ALL ON SCHEMA public TO neondb_owner;
EOF
# The dump repeats CREATE EXTENSION / COMMENT ON EXTENSION, which only the
# extension owner may run; drop those lines, as Neon's state already has them.
grep -v -E '^(CREATE EXTENSION|COMMENT ON EXTENSION)' "$DUMP" |
  docker exec -i -e PGPASSWORD=$PW "$NAME" psql -v ON_ERROR_STOP=1 -q -o /dev/null -h 127.0.0.1 -U neondb_owner -d neondb
# A schema-only dump has no rows; Neon's alembic_version holds 0003, so copy it.
docker exec "$NAME" pg_dump -U postgres --data-only --table=alembic_version scratch |
  docker exec -i -e PGPASSWORD=$PW "$NAME" psql -v ON_ERROR_STOP=1 -q -o /dev/null -h 127.0.0.1 -U neondb_owner -d neondb
docker exec "$NAME" psql -U postgres -d neondb -Atc "SELECT 'alembic_version=' || version_num FROM alembic_version"

echo "== 2. seed round-1 data (old numbering 1 = best, no capture_date)"
COLS="id, latitude, longitude, heading, pitch, rqi_score, dino_rqi_score, damage_count, damage_types, analysis_metadata, pano_id, created_at"
docker exec "$SRC_CONTAINER" psql -U postgres -d smooth_route -c \
  "\copy (SELECT id, latitude, longitude, heading, pitch, 6 - rqi_score, 6 - dino_rqi_score, damage_count, damage_types, analysis_metadata, pano_id, created_at FROM street_view_images) TO STDOUT" |
  docker exec -i -e PGPASSWORD=$PW "$NAME" psql -v ON_ERROR_STOP=1 -q -h 127.0.0.1 -U neondb_owner -d neondb \
    -c "\copy street_view_images ($COLS) FROM STDIN"
docker exec "$NAME" psql -U postgres -d neondb -Atc "SELECT 'seeded rows=' || count(*) FROM street_view_images"

echo "== 3. read-only web role, created on the round-1 schema (docs/SECURITY.md item 7)"
# GRANT ... ON ALL TABLES covers only tables that exist now; the DEFAULT
# PRIVILEGES line covers tables neondb_owner creates later (road_segments, 0005).
psql_su -d neondb <<EOF
CREATE ROLE web_ro LOGIN PASSWORD '$PW';
GRANT CONNECT ON DATABASE neondb TO web_ro;
GRANT USAGE ON SCHEMA public TO web_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO web_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public GRANT SELECT ON TABLES TO web_ro;
ALTER ROLE web_ro SET statement_timeout = '5s';
EOF

echo "== 4. publish.py --dry-run, then for real (same command as the release)"
PUBLISH_DATABASE_URL="$OWNER_URL" "$PY" scripts/publish.py --dry-run
PUBLISH_DATABASE_URL="$OWNER_URL" "$PY" scripts/publish.py
docker exec "$NAME" psql -U postgres -d neondb -Atc \
  "SELECT 'alembic_version=' || version_num FROM alembic_version;
   SELECT 'points=' || count(*) || ' dated=' || count(capture_date) || ' rqi ' || min(dino_rqi_score) || '..' || max(dino_rqi_score) FROM street_view_images;
   SELECT 'segments=' || count(*) || ' rated=' || count(rqi) FROM road_segments;
   SELECT 'image_url set=' || count(image_url) FROM street_view_images;"

cat <<EOF

Rehearsal DB ready. Start the read-only API against it (Vercel dependency set):
  cd backend && PUBLIC_READ_ONLY=1 RUN_MIGRATIONS_ON_STARTUP=false GOOGLE_MAPS_API_KEY= \\
    ALLOWED_ORIGINS=https://simaut.hu DATABASE_URL=postgresql://web_ro:$PW@127.0.0.1:$PORT/neondb \\
    uv run --no-project --with-requirements requirements.txt python -m uvicorn app.main:app --port 8006
then:   python3 scripts/smoke_public_api.py http://127.0.0.1:8006 --origin https://simaut.hu
remove: scripts/release_rehearsal.sh --down
EOF
