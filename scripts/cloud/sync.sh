#!/usr/bin/env bash
# Move data between the owner's Mac, S3 and the workstation. Plan by default; APPLY=1 runs.
#
#  On the Mac (through the owner's line, THROTTLED to SYNC_KBPS):
#    APPLY=1 scripts/cloud/sync.sh mac-push    data/ + ml caches + DB dump -> S3; hands the DB to the cloud
#    APPLY=1 scripts/cloud/sync.sh mac-pull    S3 -> data/ + DB (local backup first); takes the DB back
#    APPLY=1 scripts/cloud/sync.sh mac-fetch   cloud branches (git bundle) -> refs/remotes/cloud/*
#  On the workstation (in-region, fast, free transfer):
#    APPLY=1 scripts/cloud/sync.sh ws-pull     S3 -> data/ + restore the DB
#    APPLY=1 scripts/cloud/sync.sh ws-push     data/ + DB dump -> S3; hands the DB back to the Mac
#    APPLY=1 scripts/cloud/sync.sh ws-bundle   claude/* branches -> S3 as a git bundle (no git push)
#
# One DB writer at a time: s3://<bucket>/state/db-primary says "mac" or "ws".
# mac-push needs "mac" (or no marker); ws-push needs "ws". FORCE=1 overrides.
# Run the Mac side overnight:  caffeinate -i env APPLY=1 scripts/cloud/sync.sh mac-push
. "$(dirname "$0")/lib.sh"
cd "$HERE/../.." || exit 1   # repo root

cmd=${1:-}
case "$cmd" in ws-*) AWS_PROFILE_NAME="" ;; esac   # the instance uses its IAM role
BUCKET=$(bucket_name)
S3=s3://$BUCKET
DB_CONTAINER=${DB_CONTAINER:-smooth-route-db-1}
DUMP=data/backups/sync_smooth_route.dump
# data/backups and data/static stay local; tracked ML files come via git.
DATA_EXCLUDES=(--exclude "backups/*" --exclude "static/*" --exclude ".DS_Store")
ML_EXCLUDES=(--exclude "rqi_model.joblib" --exclude "dataset.csv")

# Throttle without touching ~/.aws/config: a private copy with s3.max_bandwidth set.
slow() {
  local cfg; cfg=$(mktemp)
  cp "${AWS_CONFIG_FILE:-$HOME/.aws/config}" "$cfg"
  AWS_CONFIG_FILE=$cfg aws configure set s3.max_bandwidth "${SYNC_KBPS}KB/s" --profile "$AWS_PROFILE_NAME"
  AWS_CONFIG_FILE=$cfg aws configure set s3.max_concurrent_requests 2 --profile "$AWS_PROFILE_NAME"
  AWS_CONFIG_FILE=$cfg "$@"
  rm -f "$cfg"
}

primary() { capture "mac" aws_ s3 cp "$S3/state/db-primary" - 2>/dev/null || echo mac; }
set_primary() { local f; f=$(mktemp); echo "$1" > "$f"; run aws_ s3 cp "$f" "$S3/state/db-primary"; rm -f "$f"; }
need_primary() {
  local p; p=$(primary)
  [[ "$p" == "$1" || "${FORCE:-0}" == 1 ]] && return 0
  echo "DB primary is '$p', not '$1': the other side owns the DB. Sync from there first, or FORCE=1."
  exit 1
}

dump_db() { mkdir -p data/backups; run sh -c "docker exec $DB_CONTAINER pg_dump -U postgres -Fc smooth_route > $DUMP"; }
restore_db() {
  run sh -c "docker exec $DB_CONTAINER pg_dump -U postgres -Fc smooth_route > data/backups/pre_sync_restore_\$(date +%Y%m%d%H%M).dump"
  run sh -c "docker exec -i $DB_CONTAINER pg_restore -U postgres -d smooth_route --clean --if-exists --no-owner < $DUMP"
}

case "$cmd" in
  mac-push)
    need_primary mac
    dump_db
    say "upload at ${SYNC_KBPS} KB/s (first run ~1.4 GB, about 3 h; later runs only send changes)"
    run slow aws_ s3 sync data "$S3/data" "${DATA_EXCLUDES[@]}"
    run slow aws_ s3 sync ml/cache "$S3/ml-cache" "${ML_EXCLUDES[@]}"
    run slow aws_ s3 cp "$DUMP" "$S3/db/smooth_route.dump"
    set_primary ws
    echo "DB handed to the workstation: do not write to the local DB until mac-pull." ;;
  ws-pull)
    run aws_ s3 sync "$S3/data" data
    run aws_ s3 sync "$S3/ml-cache" ml/cache
    run aws_ s3 cp "$S3/db/smooth_route.dump" "$DUMP"
    restore_db ;;
  ws-push)
    need_primary ws
    dump_db
    run aws_ s3 sync data "$S3/data" "${DATA_EXCLUDES[@]}"
    run aws_ s3 sync ml/cache "$S3/ml-cache" "${ML_EXCLUDES[@]}"
    run aws_ s3 cp "$DUMP" "$S3/db/smooth_route.dump"
    set_primary mac
    echo "DB handed back to the Mac: run mac-pull there; stop writing here." ;;
  mac-pull)
    need_primary mac
    say "download at ${SYNC_KBPS} KB/s (only what changed)"
    run slow aws_ s3 sync "$S3/data" data
    run slow aws_ s3 sync "$S3/ml-cache" ml/cache
    run slow aws_ s3 cp "$S3/db/smooth_route.dump" "$DUMP"
    restore_db ;;
  ws-bundle)
    run sh -c "git bundle create /tmp/ws.bundle \$(git for-each-ref --format='%(refname)' 'refs/heads/claude/*')"
    run aws_ s3 cp /tmp/ws.bundle "$S3/code/ws.bundle" ;;
  mac-fetch)
    run aws_ s3 cp "$S3/code/ws.bundle" /tmp/ws.bundle
    run git fetch /tmp/ws.bundle 'refs/heads/claude/*:refs/remotes/cloud/claude/*'
    echo "Review with: git log --oneline --all --remotes=cloud" ;;
  *) sed -n 2,16p "$0"; exit 1 ;;
esac
