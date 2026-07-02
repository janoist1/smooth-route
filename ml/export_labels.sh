#!/usr/bin/env bash
# Export the manually-labelled RQI ground truth from the Postgres DB to ml/labels.csv
# Run this ONCE from the project root:  bash ml/export_labels.sh
#
# It brings up the Postgres container, waits for it, and dumps the training_data
# rows that have a manual RQI score. The resulting ml/labels.csv is what the ML
# pipeline reads. This is the only step that needs your machine + Docker.

set -euo pipefail
cd "$(dirname "$0")/.."   # project root

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

OUT="ml/labels.csv"
echo ">> Dumping labelled rows to $OUT ..."
$DC exec -T db psql -U postgres -d smooth_route -v ON_ERROR_STOP=1 -c \
"\copy (SELECT image_filename, manual_rqi, tags, comment FROM training_data WHERE manual_rqi IS NOT NULL ORDER BY image_filename) TO STDOUT WITH CSV HEADER" > "$OUT"

N=$(($(wc -l < "$OUT") - 1))
echo ">> Done. Exported $N labelled rows to $OUT"
if [ "$N" -le 0 ]; then
  echo "WARNING: 0 rows exported. The DB volume may have been purged/reset." >&2
  echo "         If so, tell Claude and we'll set up a fresh labelling pass instead." >&2
fi
