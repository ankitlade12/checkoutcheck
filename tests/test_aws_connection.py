import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from checkoutcheck.aws_connection import connection_status, preflight


class AWSConnectionTests(unittest.TestCase):
    def test_wrong_account_stops_before_other_calls(self):
        with patch('checkoutcheck.aws_connection.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'Account': 'wrong', 'Arn': 'unused'})
            with self.assertRaisesRegex(ValueError, 'account mismatch'):
                preflight('personal', 'us-east-1', 'expected', Path('infra/aws-poc.json'))
            self.assertEqual(run.call_count, 1)

    def test_status_is_historical_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(connection_status(directory), {'status': 'not_checked'})
            report = dict(profile='personal', region='us-east-1', account_suffix='0000', identity_type='iam')
            path = Path(directory) / 'aws-connection.json'
            for hours, status in [(0, 'checked'), (2, 'recheck_required')]:
                report['checked_at'] = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                path.write_text(json.dumps(report))
                self.assertEqual(connection_status(directory)['status'], status)
            path.write_text('{broken')
            self.assertEqual(connection_status(directory), {'status': 'not_checked'})
