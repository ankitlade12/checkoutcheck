# Private AWS deployment

The current POC has been exercised on AWS; see [verification](../docs/technical-report.md). These instructions create your own private deployment. Deployment records, credentials, input archives and generated results are not included in Git.

## Prerequisites

- AWS CLI and the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-macos-overview.html).
- Your own AWS login profile, named `checkoutcheck-personal` for the convenience launcher. Use temporary login credentials, never source-controlled keys.
- An existing VPC/subnet with outbound internet routing. The instance has an outbound public address and no inbound security-group rules.
- A reviewed spending limit and notification address. Budget alerts are not hard caps; EBS, S3 and logs can incur charges while compute is stopped.
- Permission to provision the declared CloudFormation resources and create/pass their scoped instance role.

```bash
aws login --profile checkoutcheck-personal --region us-east-1
python -m checkoutcheck.aws_connection --expected-account YOUR_ACCOUNT_ID
```

The preflight checks account identity, template validity and default subnets. It does not provision resources or prove a cloud workload ran. The recorded connection check expires in the UI after one hour.

## Provision and record the stack

Review [aws-poc.json](aws-poc.json). This command creates billable resources:

```bash
aws cloudformation deploy --profile checkoutcheck-personal --region us-east-1 \
  --template-file infra/aws-poc.json --stack-name checkoutcheck-poc \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides VpcId=YOUR_VPC SubnetId=YOUR_SUBNET \
    MonthlyBudgetUSD=YOUR_BUDGET BudgetEmail=YOUR_EMAIL AutoStopHours=2
mkdir -p private-data
aws cloudformation describe-stacks --profile checkoutcheck-personal --region us-east-1 \
  --stack-name checkoutcheck-poc --query 'Stacks[0]' --output json \
  > private-data/aws-deployment.json
```

The verified demonstration used a `t3.large`, standard CPU credits, a 40 GB encrypted volume, a two-hour stop timer on every boot and a $10 monthly budget alert. The alert fires at 80% of that threshold; it is not enforcement. Record the resolved AMI, instance, bucket and log group from your actual stack.

## Install source and authorized originals

With actual local evaluations already recorded, create a fresh private release directory:

```bash
python -m checkoutcheck.release --output artifacts/release-name
```

Review the source archive and separately prepare authorized original inputs. The verified input archive contains only the `rpc/`, `retailaction/` and `models/` directories, relative to the private-data directory. Exclude AWS files, local databases, private capture records and unreviewed material. Preserve each source's license/notice files.

Upload the reviewed source archive to `code/checkoutcheck-source.zip` and the approved input archive to `inputs/original-data.tar.gz` in your stack's private bucket. Compute their SHA-256 hashes. On the instance, invoke [install-worker.sh](install-worker.sh) through an authorized SSM session with these arguments:

```bash
bash install-worker.sh YOUR_ARTIFACT_BUCKET YOUR_LOG_GROUP SOURCE_SHA256 DATA_SHA256
```

The script expects the instance's `/opt/checkoutcheck` directory created by CloudFormation. It checks both archive hashes, installs original data, builds the CPU-only container, starts it as UID 10001, binds port 8765 to host loopback and sends application logs to CloudWatch. It is a first-install script; stop jobs and review an explicit replacement procedure before updating an existing named container.

The image installs CPU-only PyTorch before the remaining pinned dependencies. The worker role reads only its own bucket's `code/` and `inputs/` prefixes. Operator login credentials are never copied into the container.

## Access and verify

For a recorded stack, `./start-aws.command` checks the account, starts EC2 and opens the private tunnel. Install the Session Manager plugin in PATH or the local ignored tools path described by the launcher.

Alternatively:

```bash
aws ssm start-session --profile checkoutcheck-personal --region us-east-1 \
  --target YOUR_INSTANCE_ID --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8765"],"localPortNumber":["8766"]}'
```

Open `http://127.0.0.1:8766`. Browser scripts accept `CHECKOUTCHECK_URL=http://127.0.0.1:8766`. Verify actual inference, exports, container health and CloudWatch log delivery. Record builds, model/source hashes and measured timings; do not relabel local reports as cloud results. The bounded image-worker timeout is ten minutes to accommodate burst-limited CPU execution.

Use an arranged screen share or an authorized operator for judges. Never open the login-free write endpoint publicly. SSM port-forwarding traffic itself is not an application audit trail.

## Backup and shutdown

Wait for jobs to reach terminal states. Use SQLite's online backup API and test restoration separately; copying a live database file can omit WAL state. Keep cloud-generated results and backups on the EC2 volume, as selected for this deployment; do not upload them to S3 without a separate decision.

```bash
aws ec2 stop-instances --profile checkoutcheck-personal --region us-east-1 \
  --instance-ids YOUR_INSTANCE_ID
aws ec2 wait instance-stopped --profile checkoutcheck-personal --region us-east-1 \
  --instance-ids YOUR_INSTANCE_ID
```

Stopping preserves the root volume and results. Deleting the stack terminates the instance and deletes that volume, including any EC2-only backup. The S3 bucket and object versions are retained deliberately and require separate cleanup. Neither shutdown nor stack deletion implies zero cost or complete data deletion.
