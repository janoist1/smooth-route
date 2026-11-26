#!/usr/bin/env bash
# Store the workstation's secrets in SSM Parameter Store (SecureString, free
# standard tier, AWS-managed KMS key). Values are read without echo and never
# written to disk, git or the shell history. Plan by default; APPLY=1 stores.
#   APPLY=1 scripts/cloud/put-secrets.sh
# Stores:
#   $PARAM_PREFIX/google_maps_api_key  the LOCAL key (Street View Static + Metadata,
#                                      Directions, Geocoding), not the Vercel server key
#   $PARAM_PREFIX/github_deploy_key    private half of a READ-ONLY deploy key
#                                      (ssh-keygen -t ed25519 -f /tmp/ws_deploy -N '';
#                                      add the .pub under GitHub repo Settings ->
#                                      Deploy keys, "Allow write access" OFF; then
#                                      delete both files)
. "$(dirname "$0")/lib.sh"

put() {  # put NAME VALUE (value passed via a file:// on a private temp file)
  local tmp; tmp=$(mktemp); chmod 600 "$tmp"; printf '%s' "$2" > "$tmp"
  run aws_ ssm put-parameter --name "$PARAM_PREFIX/$1" --type SecureString --overwrite \
    --value "file://$tmp"
  rm -f "$tmp"
}

if [[ "$APPLY" != 1 ]]; then
  echo "PLAN: would store $PARAM_PREFIX/google_maps_api_key and $PARAM_PREFIX/github_deploy_key (SecureString)"
  exit 0
fi
read -rs -p "Local Google Maps key (input hidden): " GKEY; echo
read -r -p "Path to the deploy key's PRIVATE file (e.g. /tmp/ws_deploy): " KEYFILE
[[ -n "$GKEY" && -f "$KEYFILE" ]] || { echo "missing input"; exit 1; }
put google_maps_api_key "$GKEY"
put github_deploy_key "$(cat "$KEYFILE")"
unset GKEY
echo "stored. Delete $KEYFILE and its .pub now."
