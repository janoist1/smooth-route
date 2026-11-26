#!/usr/bin/env bash
# First-boot setup of the cloud workstation (EC2 user-data, runs as root).
# Idempotent: re-run any time with  sudo bash ~/smooth-route/scripts/cloud/bootstrap.sh
# Contains NO secrets (user-data is readable from the instance metadata): it
# reads them from SSM Parameter Store with the instance role.
set -euo pipefail
exec > >(tee -a /var/log/smooth-route-bootstrap.log) 2>&1
echo "== bootstrap $(date -u +%FT%TZ)"

U=ubuntu
HOME_U=/home/$U
REPO=$HOME_U/smooth-route
PREFIX=/smooth-route
REPO_SSH=git@github.com:janoist1/smooth-route.git
MAX_UPTIME_HOURS=14
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

echo "== 1. packages: docker, git, tmux, aws cli, node 22, uv"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq docker.io docker-compose-v2 git tmux jq unzip build-essential libgl1 libglib2.0-0
usermod -aG docker $U
systemctl enable --now docker
snap list aws-cli >/dev/null 2>&1 || snap install aws-cli --classic
snap list node >/dev/null 2>&1 || snap install node --classic --channel=22
snap list astral-uv >/dev/null 2>&1 || snap install astral-uv --classic

param() {  # value of $PREFIX/$1, or empty when the parameter does not exist
  aws ssm get-parameter --region "$REGION" --name "$PREFIX/$1" --with-decryption \
    --query Parameter.Value --output text 2>/dev/null || true
}

echo "== 2. repo (read-only GitHub deploy key from SSM)"
if [[ ! -d $REPO/.git ]]; then
  KEY=$(param github_deploy_key)
  if [[ -z "$KEY" ]]; then
    echo "!! $PREFIX/github_deploy_key missing: run scripts/cloud/put-secrets.sh, then re-run bootstrap"
    exit 1
  fi
  install -d -m 700 -o $U -g $U $HOME_U/.ssh
  printf '%s\n' "$KEY" > $HOME_U/.ssh/id_ed25519
  chmod 600 $HOME_U/.ssh/id_ed25519
  # GitHub's published ed25519 host key (docs.github.com "GitHub's SSH key fingerprints").
  echo "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" \
    > $HOME_U/.ssh/known_hosts
  chown -R $U:$U $HOME_U/.ssh
  sudo -u $U git clone "$REPO_SSH" $REPO
fi

echo "== 3. .env (local key + local DB; mode 600; never committed)"
if [[ ! -f $REPO/.env ]]; then
  GKEY=$(param google_maps_api_key)
  umask 077
  cat > $REPO/.env <<ENV
GOOGLE_MAPS_API_KEY=$GKEY
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/smooth_route
AUTH_MODE=disabled
ENV
  umask 022
  chown $U:$U $REPO/.env
fi

echo "== 4. PostGIS (docker compose, :5433 on this box only; the SG has no inbound rules)"
(cd $REPO && docker compose up -d db)

echo "== 5. Python venv (CPU torch; same pins as the owner's Mac so the joblib artifact loads)"
sudo -u $U -H bash -lc "cd $REPO && [ -x .venv/bin/python ] || uv venv --python 3.14 .venv"
sudo -u $U -H bash -lc "cd $REPO && uv pip install --python .venv/bin/python \
  --index-url https://download.pytorch.org/whl/cpu torch==2.9.1 torchvision"
sudo -u $U -H bash -lc "cd $REPO && uv pip install --python .venv/bin/python \
  -e 'backend[test]' transformers==4.57.3 scikit-learn==1.9.0 pandas scipy joblib"

echo "== 6. frontend deps"
sudo -u $U -H bash -lc "cd $REPO/frontend && npm ci --no-audit --no-fund"

echo "== 7. Claude Code (native installer, as $U, never root)"
sudo -u $U -H bash -lc 'command -v claude >/dev/null || curl -fsSL https://claude.ai/install.sh | bash'

echo "== 8. hard uptime cap: power off after ${MAX_UPTIME_HOURS} h unless ~/keep-awake is newer than 2 h"
install -m 755 $REPO/scripts/cloud/autostop.sh /usr/local/bin/smooth-route-autostop
cat > /etc/systemd/system/smooth-route-autostop.service <<UNIT
[Unit]
Description=Stop the workstation after MAX_UPTIME_HOURS
[Service]
Type=oneshot
Environment=MAX_UPTIME_HOURS=$MAX_UPTIME_HOURS
ExecStart=/usr/local/bin/smooth-route-autostop
UNIT
cat > /etc/systemd/system/smooth-route-autostop.timer <<UNIT
[Unit]
Description=Check the uptime cap every 10 minutes
[Timer]
OnBootSec=10min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now smooth-route-autostop.timer

echo "== done. Next (owner, once): scripts/cloud/ws.sh connect; sudo -iu ubuntu; cd smooth-route;"
echo "   scripts/cloud/sync.sh ws-pull; claude   (log in; see docs/CLOUD_WORKSTATION.md)"
