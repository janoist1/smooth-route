#!/usr/bin/env bash
# Create the cloud workstation. Default: print the plan (no AWS call).
#   scripts/cloud/create.sh                 # plan
#   APPLY=1 scripts/cloud/create.sh         # create (asks to confirm)
# Optional: BUDGET_EMAIL=you@example.com adds a monthly AWS Budget alert.
# Run put-secrets.sh first: bootstrap reads the secrets from SSM on first boot.
. "$(dirname "$0")/lib.sh"

confirm "Creates an EC2 instance (~\$0.24/h while running), a 60 GB disk, an S3 bucket, an IAM role."
BUCKET=$(bucket_name)
ACCOUNT=$(account_id)

say "1. S3 bucket $BUCKET (private, encrypted, versioned: a bad sync can be undone)"
run aws_ s3api create-bucket --bucket "$BUCKET" \
  --create-bucket-configuration "LocationConstraint=$REGION"
run aws_ s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
run aws_ s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
run aws_ s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
run aws_ s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
  '{"Rules":[{"ID":"old-versions-30d","Status":"Enabled","Filter":{},"NoncurrentVersionExpiration":{"NoncurrentDays":30}}]}'

say "2. IAM role $NAME: SSM shell + its own parameters + its own bucket, nothing else"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
POLICY=$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"ReadOwnParams","Effect":"Allow","Action":["ssm:GetParameter","ssm:GetParameters","ssm:GetParametersByPath"],
  "Resource":"arn:aws:ssm:$REGION:$ACCOUNT:parameter$PARAM_PREFIX/*"},
 {"Sid":"DecryptParamsViaSsm","Effect":"Allow","Action":"kms:Decrypt","Resource":"*",
  "Condition":{"StringEquals":{"kms:ViaService":"ssm.$REGION.amazonaws.com"}}},
 {"Sid":"ListOwnBucket","Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::$BUCKET"},
 {"Sid":"ReadWriteOwnBucket","Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":"arn:aws:s3:::$BUCKET/*"}
]}
JSON
)
run aws_ iam create-role --role-name "$NAME" --assume-role-policy-document "$TRUST"
run aws_ iam attach-role-policy --role-name "$NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
run aws_ iam put-role-policy --role-name "$NAME" --policy-name "$NAME-data" --policy-document "$POLICY"
run aws_ iam create-instance-profile --instance-profile-name "$NAME"
run aws_ iam add-role-to-instance-profile --instance-profile-name "$NAME" --role-name "$NAME"

say "3. Security group with NO inbound rules (access is SSM only; outbound for apt/git/Google/Claude)"
VPC=$(capture "<default-vpc>" aws_ ec2 describe-vpcs --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
SG=$(capture "<sg-id>" aws_ ec2 create-security-group --group-name "$NAME" --vpc-id "$VPC" \
  --description "$NAME: no inbound, SSM only" --query GroupId --output text)

say "4. Instance ($INSTANCE_TYPE, Ubuntu 24.04, IMDSv2 only, encrypted gp3, OS shutdown = stop)"
AMI=$(capture "<ubuntu-24.04-ami>" aws_ ssm get-parameter --name "$AMI_PARAM" \
  --query Parameter.Value --output text)
[[ "$APPLY" == 1 ]] && sleep 10   # new instance profiles take a few seconds to propagate
ID=$(capture "<instance-id>" aws_ ec2 run-instances \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
  --iam-instance-profile "Name=$NAME" --security-group-ids "$SG" \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$DISK_GB,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" \
  --instance-initiated-shutdown-behavior stop \
  --user-data "file://$HERE/bootstrap.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
                       "ResourceType=volume,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)

say "5. Auto-stop: CPU < ${IDLE_CPU_PCT}% for ${IDLE_MINUTES} min -> stop (disk kept, compute billing ends)"
run aws_ cloudwatch put-metric-alarm --alarm-name "$NAME-idle-stop" \
  --namespace AWS/EC2 --metric-name CPUUtilization --dimensions "Name=InstanceId,Value=$ID" \
  --statistic Average --period 300 --evaluation-periods $((IDLE_MINUTES / 5)) \
  --threshold "$IDLE_CPU_PCT" --comparison-operator LessThanThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions "arn:aws:automate:$REGION:ec2:stop"

if [[ -n "${BUDGET_EMAIL:-}" ]]; then
  say "6. AWS Budget: \$$BUDGET_USD/month, e-mail at 80% actual and 100% forecast"
  run aws_ budgets create-budget --account-id "$ACCOUNT" \
    --budget "{\"BudgetName\":\"$NAME\",\"BudgetLimit\":{\"Amount\":\"$BUDGET_USD\",\"Unit\":\"USD\"},\"TimeUnit\":\"MONTHLY\",\"BudgetType\":\"COST\"}" \
    --notifications-with-subscribers \
    "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$BUDGET_EMAIL\"}]},
      {\"Notification\":{\"NotificationType\":\"FORECASTED\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":100},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$BUDGET_EMAIL\"}]}]"
else
  say "6. (skipped) AWS Budget alert: set BUDGET_EMAIL to add one"
fi

say "Done. Bootstrap runs on first boot (~10 min): scripts/cloud/ws.sh connect, then"
echo "   sudo tail -f /var/log/smooth-route-bootstrap.log"
