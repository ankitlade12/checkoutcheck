#!/bin/bash
# Invoke through SSM as root with the stack bucket, log group and SHA-256 hashes.
set -euo pipefail
bucket=$1
log_group=$2
source_sha=$3
data_sha=$4
cd /opt/checkoutcheck
aws s3 cp "s3://$bucket/code/checkoutcheck-source.zip" source.zip
aws s3 cp "s3://$bucket/inputs/original-data.tar.gz" original-data.tar.gz
echo "$source_sha  source.zip" | sha256sum -c -
echo "$data_sha  original-data.tar.gz" | sha256sum -c -
mkdir -p source data
unzip -o -q source.zip -d source
tar -xzf original-data.tar.gz -C data
chown -R 10001:10001 data
cd source
docker build -f infra/Dockerfile -t checkoutcheck:poc .
docker run -d --name checkoutcheck --restart unless-stopped \
  -p 127.0.0.1:8765:8765 -v /opt/checkoutcheck/data:/data \
  -e CHECKOUTCHECK_RUNTIME=aws_private_single_operator \
  --log-driver awslogs --log-opt awslogs-region=us-east-1 \
  --log-opt "awslogs-group=$log_group" --log-opt awslogs-stream=application \
  checkoutcheck:poc
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:8765/v1/health; then exit 0; fi
  sleep 2
done
exit 1
