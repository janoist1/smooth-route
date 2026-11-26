#!/usr/bin/env bash
# Day-to-day control from the Mac (needs the Session Manager plugin:
# brew install --cask session-manager-plugin). Plan by default; APPLY=1 runs.
#   APPLY=1 scripts/cloud/ws.sh start|stop|status|connect
# connect = a shell over SSM: no SSH key, no open port. The owner's line carries
# only the terminal text.
. "$(dirname "$0")/lib.sh"
ID=$(instance_id)
case "${1:-}" in
  start)   run aws_ ec2 start-instances --instance-ids "$ID" --query 'StartingInstances[0].CurrentState.Name' --output text ;;
  stop)    run aws_ ec2 stop-instances --instance-ids "$ID" --query 'StoppingInstances[0].CurrentState.Name' --output text ;;
  status)  run aws_ ec2 describe-instances --instance-ids "$ID" \
             --query 'Reservations[0].Instances[0].[State.Name,InstanceType,LaunchTime]' --output text ;;
  connect) run aws_ ssm start-session --target "$ID" ;;
  *) sed -n 2,6p "$0"; exit 1 ;;
esac
