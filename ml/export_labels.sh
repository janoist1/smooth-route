#!/usr/bin/env bash
# Export the manually-labelled RQI ground truth from the Postgres DB to ml/labels.csv
# Run this ONCE from the project root:  bash ml/export_labels.sh
#
# It brings up the Postgres container, waits for it, and dumps the training_data
# rows that have a manual RQI score. The resulting ml/labels.csv is what the ML
# pipeline reads. This is the only step that needs your machine + Docker.
#
# Every label written through the review page OR the quick-rate screen
# ("Gyors címkézés", /training/quick) is a training_data row with manual_rqi, so
# both are exported. Extra columns (ignored by readers that do not need them):
#   svi_id, latitude, longitude  street_view_images row of the frame, so
#                                ml/build_coords.py can place sv_* frames
#   source                       "quick" (quick-rate screen) | "review"
#
# Overrides: OUT=path/to.csv  DB_NAME=other_db  (e.g. a scratch DB for tests)

set -euo pipefail
cd "$(dirname "$0")/.."   # project root
# Compose derives the project name from the directory; pin it so a git
# worktree (different folder name) reuses the main smooth-route DB container
# instead of creating a new, empty one.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-smooth-route}"

# docker compose (v2) vs docker-compose (v1)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' found." >&2
  exit 1
fi

echo ">> Starting Postgres (db) ..."
$DC up -d db

echo ">> Waiting for Postgres to be ready ..."
for i in $(seq 1 30); do
  if $DC exec -T db pg_isready -U postgres >/dev/null 2>&1; then
    echo "   ready."
    break
  fi
  sleep 1
  [ "$i" = "30" ] && { echo "ERROR: DB did not become ready." >&2; exit 1; }
done

# ml/labels.csv is in the ML *severity* orientation (1 = best), whatever the
# canonical direction in shared/rqi_scale.json is; ml/rqi_scale.py gives the SQL
# that converts: `(6 - manual_rqi)` since the 2026-11-26 flip (5 = Kiváló in the DB).
PY="${PY:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
RQI_EXPR=$("$PY" ml/rqi_scale.py --sql td.manual_rqi)

OUT="${OUT:-ml/labels.csv}"
DB_NAME="${DB_NAME:-smooth_route}"
echo ">> Dumping labelled rows from $DB_NAME to $OUT (manual_rqi := $RQI_EXPR) ..."
$DC exec -T db psql -U postgres -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
"\copy (SELECT td.image_filename, $RQI_EXPR AS manual_rqi, td.tags, td.comment, svi.id AS svi_id, svi.latitude, svi.longitude, CASE WHEN (td.meta_data::jsonb) ? 'quick_label' THEN 'quick' ELSE 'review' END AS source FROM training_data td LEFT JOIN street_view_images svi ON svi.image_url = 'images/' || td.image_filename WHERE td.manual_rqi IS NOT NULL ORDER BY td.image_filename) TO STDOUT WITH CSV HEADER" > "$OUT"

N=$(($(wc -l < "$OUT") - 1))
Q=$(grep -c ',quick$' "$OUT" || true)
echo ">> Done. Exported $N labelled rows to $OUT ($Q from the quick-rate screen)"
echo "   Next: extract_features_v2.py -> build_coords.py (see ml/README.md)"
if [ "$N" -le 0 ]; then
  echo "WARNING: 0 rows exported. The DB volume may have been purged/reset." >&2
  echo "         If so, tell Claude and we'll set up a fresh labelling pass instead." >&2
fi
