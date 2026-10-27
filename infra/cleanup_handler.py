"""Scheduled teardown of explicitly configured CheckoutCheck resources only."""
import datetime
import json
import os

import boto3
from botocore.exceptions import ClientError


def stack_state(client, stack_id):
    try:
        return client.describe_stacks(StackName=stack_id)['Stacks'][0]['StackStatus']
    except ClientError as error:
        if error.response['Error']['Code'] == 'ValidationError' and 'does not exist' in error.response['Error']['Message']:
            return 'DELETE_COMPLETE'
        raise


def handler(event, context):
    config = json.loads(os.environ['CLEANUP_CONFIG'])
    now = datetime.datetime.now(datetime.timezone.utc)
    deadline = datetime.datetime.fromisoformat(config['not_before'])
    account = boto3.client('sts').get_caller_identity()['Account']
    if account != config['account']:
        raise ValueError('Cleanup account mismatch')
    cloudformation = boto3.client('cloudformation')
    states = {stack: stack_state(cloudformation, stack) for stack in config['stacks']}
    if event.get('dry_run') is True or now < deadline:
        result = {'dry_run': True, 'not_before': config['not_before'], 'stacks': states, 'bucket': config['bucket']}
        print(json.dumps(result))
        return result
    # Delete public networking before the worker security group it references.
    for stack, state in states.items():
        if state == 'DELETE_COMPLETE':
            continue
        if state == 'DELETE_IN_PROGRESS':
            return {'waiting': stack}
        if state not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE', 'DELETE_FAILED'):
            raise ValueError(f'Unexpected stack state: {stack}: {state}')
        cloudformation.delete_stack(StackName=stack)
        return {'deleting': stack}
    # CloudFormation deliberately retains this versioned bucket. Purge every
    # version and delete marker only after the application stacks are gone.
    s3 = boto3.client('s3')
    bucket = config['bucket']
    try:
        for page in s3.get_paginator('list_object_versions').paginate(Bucket=bucket, ExpectedBucketOwner=account):
            objects = [{'Key': item['Key'], 'VersionId': item['VersionId']}
                       for item in page.get('Versions', []) + page.get('DeleteMarkers', [])]
            for start in range(0, len(objects), 1000):
                response = s3.delete_objects(Bucket=bucket, ExpectedBucketOwner=account,
                                             Delete={'Objects': objects[start:start + 1000], 'Quiet': True})
                if response.get('Errors'):
                    raise RuntimeError(f"Bucket deletion failed: {response['Errors']}")
        for page in s3.get_paginator('list_multipart_uploads').paginate(Bucket=bucket, ExpectedBucketOwner=account):
            for upload in page.get('Uploads', []):
                s3.abort_multipart_upload(Bucket=bucket, Key=upload['Key'], UploadId=upload['UploadId'], ExpectedBucketOwner=account)
        s3.delete_bucket(Bucket=bucket, ExpectedBucketOwner=account)
    except ClientError as error:
        if error.response['Error']['Code'] != 'NoSuchBucket':
            raise
    # Delete this scheduler, function, log group and IAM roles as the last step.
    cloudformation.delete_stack(StackName=os.environ['CLEANUP_STACK'])
    return {'cleanup': 'application stacks and bucket deleted; automation teardown requested'}
