#!/usr/bin/env bash
# Remove the workstation. Plan by default; APPLY=1 runs (asks to confirm).
#   APPLY=1 scripts/cloud/teardown.sh                    # instance, alarm, SG, role, budget
#   APPLY=1 DELETE_DATA=1 DELETE_SECRETS=1 scripts/cloud/teardown.sh   # + bucket + parameters
# First bring the work home: on the box `sync.sh ws-bundle` + `sync.sh ws-push`,
# then on the Mac `sync.sh mac-fetch` + `sync.sh mac-pull`. Terminating deletes the disk.
. "$(dirname "$0")/lib.sh"
confirm "Terminates the instance and DELETES its disk."
ID=$(instance_id)
BUCKET=$(bucket_name)

say "1. instance + alarm + budget"
run aws_ ec2 terminate-instances --instance-ids "$ID"
run aws_ ec2 wait instance-terminated --instance-ids "$ID"
run aws_ cloudwatch delete-alarms --alarm-names "$NAME-idle-stop"
run aws_ budgets delete-budget --account-id "$(account_id)" --budget-name "$NAME" || true

say "2. security group + IAM role"
SG=$(capture "<sg-id>" aws_ ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)
run aws_ ec2 delete-security-group --group-id "$SG"
run aws_ iam remove-role-from-instance-profile --instance-profile-name "$NAME" --role-name "$NAME"
run aws_ iam delete-instance-profile --instance-profile-name "$NAME"
run aws_ iam delete-role-policy --role-name "$NAME" --policy-name "$NAME-data"
run aws_ iam detach-role-policy --role-name "$NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
run aws_ iam delete-role --role-name "$NAME"

if [[ "${DELETE_DATA:-0}" == 1 ]]; then
  say "3. bucket $BUCKET (all versions)"
  # Versioned: every old version must go first. S3 console -> bucket -> Empty
  # does that in one click (deliberately not scripted: it is irreversible).
  if [[ "$APPLY" == 1 ]]; then read -r -p "Emptied $BUCKET in the S3 console? [y/N] " ok; [[ "$ok" == y ]] || exit 1; fi
  run aws_ s3api delete-bucket --bucket "$BUCKET"
else
  say "3. (kept) bucket $BUCKET: DELETE_DATA=1 to remove (~\$0.04/month for 1.5 GB)"
fi
if [[ "${DELETE_SECRETS:-0}" == 1 ]]; then
  say "4. SSM parameters under $PARAM_PREFIX"
  run aws_ ssm delete-parameters --names "$PARAM_PREFIX/google_maps_api_key" "$PARAM_PREFIX/github_deploy_key"
  echo "   Also remove the deploy key in GitHub (repo Settings -> Deploy keys)."
else
  say "4. (kept) SSM parameters: DELETE_SECRETS=1 to remove"
fi
