#!/usr/bin/env bash
# Hard per-boot cap, run every 10 min by a systemd timer (installed by bootstrap.sh).
# Powers off (= EC2 stop: disk kept, compute billing ends) once the box has been
# up MAX_UPTIME_HOURS, unless /home/ubuntu/keep-awake was touched in the last
# 2 hours (`touch ~/keep-awake` to extend). The CloudWatch idle alarm covers the
# other case: nothing running.
set -euo pipefail
MAX_UPTIME_HOURS=${MAX_UPTIME_HOURS:-14}
FLAG=/home/ubuntu/keep-awake
up_s=$(cut -d. -f1 /proc/uptime)
(( up_s < MAX_UPTIME_HOURS * 3600 )) && exit 0
if [[ -f $FLAG ]] && (( $(date +%s) - $(stat -c %Y "$FLAG") < 7200 )); then exit 0; fi
logger -t smooth-route-autostop "up ${up_s}s > ${MAX_UPTIME_HOURS}h, no keep-awake: powering off"
systemctl poweroff
