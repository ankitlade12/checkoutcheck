"""Read-only AWS preflight; credentials remain in the AWS CLI credential store."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def preflight(profile, region, expected_account, template):
    def aws(*args):
        result = subprocess.run(['aws', *args, '--profile', profile, '--region', region,
                                 '--output', 'json', '--no-cli-pager'],
                                capture_output=True, text=True, timeout=60, check=True)
        return json.loads(result.stdout)

    identity = aws('sts', 'get-caller-identity')
    if identity['Account'] != expected_account:
        raise ValueError('AWS account mismatch; refusing to inspect another account')
    validation = aws('cloudformation', 'validate-template', '--template-body', 'file://' + str(template.resolve()))
    subnets = aws('ec2', 'describe-subnets', '--filters', 'Name=default-for-az,Values=true')['Subnets']
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'profile': profile,
            'region': region, 'account_suffix': identity['Account'][-4:],
            'identity_type': 'root' if identity['Arn'].endswith(':root') else 'iam',
            'template_validated': bool(validation), 'deployment_verified': False,
            'subnets': [{'id': s['SubnetId'], 'vpc': s['VpcId'], 'zone': s['AvailabilityZone']} for s in subnets]}


def connection_status(directory):
    # Historical evidence only: do not imply the cached login is still valid.
    try:
        report = json.loads((Path(directory) / 'aws-connection.json').read_text())
        checked = datetime.fromisoformat(report['checked_at'])
        age = (datetime.now(timezone.utc) - checked).total_seconds()
        return {'status': 'checked' if 0 <= age < 3600 else 'recheck_required',
                **{k: report[k] for k in ('checked_at', 'profile', 'region', 'account_suffix', 'identity_type')}}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'not_checked'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='checkoutcheck-personal')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--expected-account', required=True)
    parser.add_argument('--directory', default=os.environ.get('CHECKOUTCHECK_DATA', 'private-data'))
    args = parser.parse_args()
    directory = Path(args.directory)
    destination = directory / 'aws-connection.json'
    try:
        report = preflight(args.profile, args.region, args.expected_account,
                           Path(__file__).resolve().parents[1] / 'infra/aws-poc.json')
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    directory.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(destination)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
