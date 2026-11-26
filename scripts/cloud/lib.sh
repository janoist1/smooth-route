# Helpers for scripts/cloud/*. Default is a PLAN: AWS commands are printed, not
# run. Set APPLY=1 to execute them. Nothing calls AWS unless APPLY=1.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=config.sh
. "$HERE/config.sh"

APPLY=${APPLY:-0}

# On the Mac: the owner's CLI profile. On the instance (AWS_PROFILE_NAME=""): its IAM role.
aws_() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then aws --profile "$AWS_PROFILE_NAME" --region "$REGION" "$@"
  else aws --region "$REGION" "$@"; fi
}

plan_line() { printf 'PLAN:'; printf ' %q' "$@"; echo; }

# run CMD...      execute (APPLY=1) or print the command
run() {
  if [[ "$APPLY" == 1 ]]; then "$@"; else plan_line "$@"; fi
}

# capture PLACEHOLDER CMD...   stdout of CMD (APPLY=1), or the placeholder in a plan
capture() {
  local placeholder=$1; shift
  if [[ "$APPLY" == 1 ]]; then "$@"; else plan_line "$@" >&2; echo "$placeholder"; fi
}

say() { printf '\n== %s\n' "$*"; }

account_id() { capture "<account-id>" aws_ sts get-caller-identity --query Account --output text; }
bucket_name() { echo "${NAME}-$(account_id)-${REGION}"; }

instance_id() {
  capture "<instance-id>" aws_ ec2 describe-instances \
    --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[].Instances[].InstanceId' --output text
}

confirm() {
  [[ "$APPLY" == 1 ]] || return 0
  read -r -p "$1 Type the name '$NAME' to continue: " answer
  [[ "$answer" == "$NAME" ]] || { echo "aborted"; exit 1; }
}
