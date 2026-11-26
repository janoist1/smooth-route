#!/usr/bin/env bash
# Post-process newly collected frames, incrementally (one command):
#
#   bash backend/scripts/postprocess_new_frames.sh        # or: make postprocess
#
#   1. fresh pg_dump        -> data/backups/pre_postprocess_<ts>.dump (keeps the last 3)
#   2. frame quality        ml/frame_quality.py all + write --commit (only new/changed rows)
#   3. DINO re-score        scripts/rescore_dino.py (only frames without the live
#                           artifact's marker; skips frame_quality.usable = false)
#   4. road segments        scripts/build_segments.py --cached-only (never fetches
#                           OSM; frames on uncached tiles wait for the next run)
#   5. collector report     scripts/collect_network.py --report
#   6. summary              frames created since $SINCE: usable / reasons / classes
#
# Safe while the collector is still inserting: every step only touches rows
# that exist when it reads them, frames whose image file is not on disk yet are
# left for the next run, and every step is idempotent (rerun any time).
#
# Env: SINCE="2026-11-26 05:20" (summary window, UTC like created_at), PY=<python>, SKIP_DUMP=1 (tests only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MAIN="$(cd "$(git rev-parse --path-format=absolute --git-common-dir)/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$MAIN/.venv/bin/python"     # git worktrees share the main checkout's venv
export DATA_DIR="${DATA_DIR:-$MAIN/data}"
export HF_HUB_OFFLINE=1
SINCE="${SINCE:-$(date +%Y-%m-%d) 00:00}"
TS="$(date +%Y%m%d%H%M)"
DB="docker exec -i smooth-route-db-1"
psql_q() { $DB psql -U postgres -d smooth_route -At -F ' | ' -c "$1"; }
step() { echo; echo "== $(date +%H:%M:%S) $*"; }

step "1/6 backup"
DUMP="$DATA_DIR/backups/pre_postprocess_$TS.dump"
if [ -z "${SKIP_DUMP:-}" ]; then
  mkdir -p "$DATA_DIR/backups"
  $DB pg_dump -U postgres -Fc smooth_route > "$DUMP"
  [ -s "$DUMP" ] || { echo "backup is empty - abort"; exit 1; }
  ls -1t "$DATA_DIR"/backups/pre_postprocess_*.dump | tail -n +4 | xargs -r rm -f
  echo "backup: $DUMP ($(du -h "$DUMP" | cut -f1))"
fi

step "2/6 frame quality"
"$PY" ml/frame_quality.py all | grep -v '^ *[0-9]* ~ ' | tail -22
"$PY" ml/frame_quality.py write --commit --backup "$DUMP" | grep -E '^\[write\] (incremental|COMMITTED|nothing|note)'

step "3/6 DINO re-score (new frames)"
(cd backend && "$PY" scripts/rescore_dino.py 2>&1 | grep -v -i warn | tail -15)

step "4/6 road segments (cached OSM tiles only)"
(cd backend && "$PY" scripts/build_segments.py --cached-only 2>&1 | tail -25)

step "5/6 collector report"
(cd backend && "$PY" scripts/collect_network.py --report 2>&1 | tail -15) || echo "(report failed - non-fatal)"

step "6/6 summary of frames created since $SINCE"
psql_q "SELECT count(*) AS frames,
               count(*) FILTER (WHERE analysis_metadata->'frame_quality' IS NOT NULL) AS with_fq,
               count(*) FILTER (WHERE (analysis_metadata->'frame_quality'->>'usable')::boolean IS FALSE) AS unusable,
               count(*) FILTER (WHERE analysis_metadata->>'dino_artifact' IS NOT NULL) AS scored
        FROM street_view_images WHERE created_at >= '$SINCE'" | sed 's/^/frames | with_fq | unusable | scored: /'
echo "unusable by reason:"
psql_q "SELECT r, count(*) FROM street_view_images s,
               json_array_elements_text(s.analysis_metadata->'frame_quality'->'reasons') r
        WHERE s.created_at >= '$SINCE' GROUP BY r ORDER BY 2 DESC"
echo "class distribution of usable scored frames (canonical scale, shared/rqi_scale.json):"
psql_q "SELECT dino_rqi_score, count(*) FROM street_view_images
        WHERE created_at >= '$SINCE' AND analysis_metadata->>'dino_artifact' IS NOT NULL
          AND COALESCE((analysis_metadata->'frame_quality'->>'usable')::boolean, true)
        GROUP BY 1 ORDER BY 1"
echo "road segments: $(psql_q 'SELECT count(*) FROM road_segments')"
