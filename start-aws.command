#!/bin/bash
# Private AWS access. Starting a stopped worker incurs compute charges.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f private-data/aws-deployment.json ]; then
  echo 'No local AWS stack record. Follow infra/aws-poc-operations.md to deploy and save stack outputs first.'
  exit 1
fi
eval "$(python3 - <<'PY'
import json, shlex
from pathlib import Path
stack=json.loads(Path('private-data/aws-deployment.json').read_text())
outputs={row['OutputKey']:row['OutputValue'] for row in stack['Outputs']}
for name,value in [('worker_id',outputs['InstanceId']),('expected_account',stack['StackId'].split(':')[4])]:
 print(name+'='+shlex.quote(value))
PY
)"
actual_account=$(aws sts get-caller-identity --profile checkoutcheck-personal --region us-east-1 --query Account --output text)
if [ "$actual_account" != "$expected_account" ]; then
  echo 'Personal account mismatch. Refusing to start the worker.'
  exit 1
fi
export PATH="$PWD/private-data/tools/sessionmanager-bundle/bin:$PATH"
command -v session-manager-plugin >/dev/null
aws ec2 start-instances --profile checkoutcheck-personal --region us-east-1 --instance-ids "$worker_id" --output json
aws ec2 wait instance-running --profile checkoutcheck-personal --region us-east-1 --instance-ids "$worker_id"
for attempt in $(seq 1 60); do
  ping=$(aws ssm describe-instance-information --profile checkoutcheck-personal --region us-east-1 --filters "Key=InstanceIds,Values=$worker_id" --query 'InstanceInformationList[0].PingStatus' --output text)
  if [ "$ping" = Online ]; then break; fi
  sleep 3
done
echo 'Open http://127.0.0.1:8766 after the tunnel reports it is listening.'
echo 'Keep this terminal open. Compute automatically stops two hours after boot.'
exec aws ssm start-session --profile checkoutcheck-personal --region us-east-1 --target "$worker_id" \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8765"],"localPortNumber":["8766"]}'
