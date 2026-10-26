import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class DeploymentContractTests(unittest.TestCase):
    def test_private_poc_has_no_inbound_ports_and_encrypted_storage(self):
        template=json.loads((ROOT/'infra/aws-poc.json').read_text())
        resources=template['Resources']
        self.assertEqual(resources['Firewall']['Properties']['SecurityGroupIngress'],[])
        self.assertTrue(resources['Worker']['Properties']['BlockDeviceMappings'][0]['Ebs']['Encrypted'])
        self.assertEqual(resources['Worker']['Properties']['MetadataOptions']['HttpTokens'],'required')
        self.assertTrue(all(resources['Artifacts']['Properties']['PublicAccessBlockConfiguration'].values()))
        self.assertNotIn('Default',template['Parameters']['MonthlyBudgetUSD'])
        self.assertNotIn('Default',template['Parameters']['BudgetEmail'])

    def test_instance_cannot_write_code_or_all_buckets(self):
        template=json.loads((ROOT/'infra/aws-poc.json').read_text())
        statements=template['Resources']['WorkerRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        writes=[s for s in statements if 's3:PutObject' in s['Action']]
        self.assertEqual(len(writes),1)
        self.assertEqual(writes[0]['Resource'],{'Fn::Sub':'${Artifacts.Arn}/outputs/*'})
