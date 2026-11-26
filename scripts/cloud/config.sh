# Shared settings for scripts/cloud/*. Override any of them in the environment.
# Nothing here is secret: secrets live in SSM Parameter Store (put-secrets.sh).
AWS_PROFILE_NAME=${AWS_PROFILE_NAME:-i}
REGION=${REGION:-eu-central-1}             # Frankfurt: next to Neon
NAME=${NAME:-smooth-route-ws}              # tag / role / alarm / SG name
INSTANCE_TYPE=${INSTANCE_TYPE:-m7i.xlarge} # 4 vCPU, 16 GB, x86 (postgis image is amd64-only)
DISK_GB=${DISK_GB:-60}                     # gp3, encrypted; images 0.85 GB + venv/torch ~6 GB
PARAM_PREFIX=${PARAM_PREFIX:-/smooth-route}
IDLE_CPU_PCT=${IDLE_CPU_PCT:-3}            # stop when average CPU stays below this…
IDLE_MINUTES=${IDLE_MINUTES:-60}           # …for this long (CloudWatch alarm)
MAX_UPTIME_HOURS=${MAX_UPTIME_HOURS:-14}   # hard cap per boot (on-instance timer)
SYNC_KBPS=${SYNC_KBPS:-120}                # Mac <-> S3 cap in KB/s (~40% of a 2.5 Mbit/s uplink)
BUDGET_USD=${BUDGET_USD:-40}               # monthly AWS Budget alert (needs BUDGET_EMAIL)
REPO_SSH=${REPO_SSH:-git@github.com:janoist1/smooth-route.git}
# Ubuntu 24.04 LTS, amd64, resolved at apply time from Canonical's public SSM parameter.
AMI_PARAM=/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id
