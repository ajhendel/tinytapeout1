#!/usr/bin/env bash
# Launch a self-expiring AWS F2 FPGA instance for the WP3 pilot.
#
# Read docs/FPGA_PILOT.md before running this. F2 is the right tool for exactly
# two items in WP3 and the wrong tool for the rest, and it costs 1.98 USD an
# hour whether or not anyone is looking at it.
#
# The lease is baked into the instance, not into the operator's memory. The
# instance shuts itself down after LEASE_HOURS whatever happens to this laptop,
# the network, or the session that started it. An instance without a lease is an
# orphan waiting to happen.
#
# Usage:
#   AWS_PROFILE=mambik tools/aws/launch_f2.sh                 # 4 hour lease
#   AWS_PROFILE=mambik LEASE_HOURS=8 tools/aws/launch_f2.sh
#   AWS_PROFILE=mambik tools/aws/launch_f2.sh --terminate     # kill ours, now

set -euo pipefail

REGION="${REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-f2.6xlarge}"
LEASE_HOURS="${LEASE_HOURS:-4}"
PROJECT_TAG="tinytapeout1"
NAME_TAG="tinytapeout1-fpga-pilot"

find_ours() {
  aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" \
              "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name,LaunchTime,PublicIpAddress]' \
    --output text
}

if [[ "${1:-}" == "--list" ]]; then
  find_ours
  exit 0
fi

if [[ "${1:-}" == "--terminate" ]]; then
  ids=$(find_ours | awk '{print $1}')
  if [[ -z "$ids" ]]; then echo "nothing tagged Project=$PROJECT_TAG is running"; exit 0; fi
  echo "terminating: $ids"
  aws ec2 terminate-instances --region "$REGION" --instance-ids $ids \
      --query 'TerminatingInstances[].[InstanceId,CurrentState.Name]' --output text
  exit 0
fi

existing=$(find_ours)
if [[ -n "$existing" ]]; then
  echo "An instance for this project already exists. Refusing to launch a second."
  echo "$existing"
  echo "Use --terminate first, or --list to inspect."
  exit 1
fi

# Latest FPGA Developer AMI. It carries Vivado, licensed for use on F instances,
# plus the aws-fpga developer kit prerequisites.
AMI=$(aws ec2 describe-images --region "$REGION" --owners aws-marketplace \
        --filters "Name=name,Values=FPGA Developer AMI (Ubuntu)*" \
        --query 'reverse(sort_by(Images,&CreationDate))[0].ImageId' --output text)
echo "AMI            $AMI"
echo "instance type  $INSTANCE_TYPE"
echo "region         $REGION"
echo "lease          $LEASE_HOURS hours, enforced on the instance"

USERDATA=$(cat <<EOF
#!/bin/bash
set -x
# The lease. Two independent mechanisms, because one of them will eventually be
# the one that was misconfigured.
shutdown -h +$((LEASE_HOURS * 60))
cat > /etc/systemd/system/lease.service <<'UNIT'
[Unit]
Description=Hard lease expiry for the tinytapeout1 FPGA pilot
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'sleep $((LEASE_HOURS * 3600)); /sbin/shutdown -h now'
UNIT
systemctl enable --now lease.service

# Terminate rather than stop when the shutdown fires, so an expired lease costs
# nothing at all rather than costing EBS.
INSTANCE_ID=\$(curl -s -H "X-aws-ec2-metadata-token: \$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 modify-instance-attribute --region $REGION --instance-id \$INSTANCE_ID \
    --instance-initiated-shutdown-behavior terminate || true

su - ubuntu -c 'git clone https://github.com/aws/aws-fpga.git ~/aws-fpga' || true
EOF
)

aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --instance-initiated-shutdown-behavior terminate \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=200,VolumeType=gp3,DeleteOnTermination=true}' \
  --tag-specifications \
    "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG},{Key=Project,Value=$PROJECT_TAG},{Key=LeaseHours,Value=$LEASE_HOURS},{Key=CostCenter,Value=tinytapeout1-personal}]" \
  --user-data "$USERDATA" \
  --query 'Instances[].[InstanceId,InstanceType,State.Name]' --output text

echo
echo "Tagged Project=$PROJECT_TAG and CostCenter=tinytapeout1-personal so this"
echo "spend is separable from anything else in the account."
echo "Stop it early with: AWS_PROFILE=\$AWS_PROFILE tools/aws/launch_f2.sh --terminate"
