"""Teardown safety checks; all AWS clients are mocked, no resources deleted."""
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class CleanupTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('cleanup_handler', Path(__file__).resolve().parents[1] / 'infra/cleanup_handler.py')
        self.module = importlib.util.module_from_spec(spec)
        # boto3 is supplied by Lambda, not an application dependency.
        self.boto = types.ModuleType('boto3')
        exceptions = types.ModuleType('botocore.exceptions')
        class ClientError(Exception):
            def __init__(self, response):
                self.response = response
        exceptions.ClientError = ClientError
        with patch.dict(sys.modules, {'boto3': self.boto, 'botocore.exceptions': exceptions}):
            spec.loader.exec_module(self.module)
        self.clients = {name: Mock() for name in ['sts', 'cloudformation', 's3']}
        self.boto.client = lambda name: self.clients[name]
        self.clients['sts'].get_caller_identity.return_value = {'Account': 'personal'}
        self.clients['cloudformation'].describe_stacks.return_value = {'Stacks': [{'StackStatus': 'CREATE_COMPLETE'}]}
        self.config = {'account': 'personal', 'not_before': '2000-01-01T00:00:00+00:00', 'stacks': ['public', 'private'], 'bucket': 'project-only'}
        self.env = patch.dict(os.environ, {'CLEANUP_CONFIG': json.dumps(self.config), 'CLEANUP_STACK': 'automation'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_dry_run_never_deletes(self):
        self.module.handler({'dry_run': True}, None)
        self.clients['cloudformation'].delete_stack.assert_not_called()
        self.clients['s3'].delete_bucket.assert_not_called()

    def test_cannot_run_before_deadline(self):
        self.config['not_before'] = '2999-01-01T00:00:00+00:00'
        os.environ['CLEANUP_CONFIG'] = json.dumps(self.config)
        self.module.handler({}, None)
        self.clients['cloudformation'].delete_stack.assert_not_called()

    def test_wrong_account_rejected(self):
        self.clients['sts'].get_caller_identity.return_value = {'Account': 'other'}
        with self.assertRaisesRegex(ValueError, 'account mismatch'):
            self.module.handler({}, None)
        self.clients['cloudformation'].delete_stack.assert_not_called()

    def test_public_deleted_before_private(self):
        self.module.handler({}, None)
        self.clients['cloudformation'].delete_stack.assert_called_once_with(StackName='public')
        self.clients['s3'].delete_bucket.assert_not_called()

    def test_waits_for_stack_deletion(self):
        self.clients['cloudformation'].describe_stacks.return_value = {'Stacks': [{'StackStatus': 'DELETE_IN_PROGRESS'}]}
        self.module.handler({}, None)
        self.clients['cloudformation'].delete_stack.assert_not_called()

    def test_bucket_failure_prevents_automation_removal(self):
        self.clients['cloudformation'].describe_stacks.return_value = {'Stacks': [{'StackStatus': 'DELETE_COMPLETE'}]}
        self.clients['s3'].get_paginator.return_value.paginate.return_value = [{'Versions': [{'Key': 'a', 'VersionId': '1'}], 'DeleteMarkers': [{'Key': 'a', 'VersionId': '2'}]}]
        self.clients['s3'].delete_objects.return_value = {'Errors': [{'Code': 'AccessDenied'}]}
        with self.assertRaises(RuntimeError):
            self.module.handler({}, None)
        self.clients['cloudformation'].delete_stack.assert_not_called()

    def test_versions_and_markers_deleted_before_final_cleanup(self):
        self.clients['cloudformation'].describe_stacks.return_value = {'Stacks': [{'StackStatus': 'DELETE_COMPLETE'}]}
        self.clients['s3'].get_paginator.return_value.paginate.return_value = [{'Versions': [{'Key': 'a', 'VersionId': '1'}], 'DeleteMarkers': [{'Key': 'a', 'VersionId': '2'}]}]
        self.clients['s3'].delete_objects.return_value = {}
        self.module.handler({}, None)
        self.clients['s3'].delete_objects.assert_called_once_with(Bucket='project-only', ExpectedBucketOwner='personal', Delete={'Objects': [{'Key': 'a', 'VersionId': '1'}, {'Key': 'a', 'VersionId': '2'}], 'Quiet': True})
        self.clients['s3'].delete_bucket.assert_called_once_with(Bucket='project-only', ExpectedBucketOwner='personal')
        self.clients['cloudformation'].delete_stack.assert_called_once_with(StackName='automation')
