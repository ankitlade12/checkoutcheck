"""API integration checks use temporary metadata, never a bundled dataset."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from checkoutcheck import server
from checkoutcheck.evaluator import canonical
from test_evaluator import bundle, case, inputs


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.old=server.DATA
        server.DATA=Path(self.temporary.name)
        server.initialize()
        self.client=TestClient(server.app)
        self.headers={'X-CheckoutCheck':'local'}

    def tearDown(self):
        self.client.close()
        server.DATA=self.old
        self.temporary.cleanup()

    def register(self):
        # Metadata-only test. No video bytes or observations are manufactured.
        asset={'id':'asset','duration_ms':4000,'sha256':'a'*64}
        with server.db() as conn:conn.execute('INSERT INTO assets VALUES (?,?)',('asset',canonical(asset)))
        request={'asset_id':'asset','title':'API contract test','annotation':case(),'inputs':inputs()}
        response=self.client.post('/v1/cases',json=request,headers=self.headers)
        self.assertEqual(response.status_code,201,response.text)
        response=self.client.post('/v1/suites',json={'name':'Test','case_ids':['case'],
            'policy':{'tolerance_ms':1000,'cooldown_ms':2000,'abstention_routes_to_review':True}},headers=self.headers)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def test_fresh_workspace_has_no_dataset(self):
        response=self.client.get('/v1/state')
        self.assertEqual(response.status_code,200)
        for field in ('assets','cases','suites','runs'):self.assertEqual(response.json()[field],[])

    def test_perception_requires_original_dataset(self):
        self.assertFalse(self.client.get('/v1/perception').json()['available'])
        response=self.client.post('/v1/perception/runs',json={
            'model':'foreground-components-v1','idempotency_key':'no-data'},headers=self.headers)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.get('/v1/perception/images/1').status_code,404)

    def test_missing_model_and_video_sources_report_unavailable(self):
        response=self.client.post('/v1/perception/runs',json={'model':'fasterrcnn-rpc-v1','idempotency_key':'missing-model'},headers=self.headers)
        self.assertEqual(response.status_code,409)
        self.assertFalse(self.client.get('/v1/videos').json()['available'])
        self.assertEqual(self.client.get('/v1/videos/unknown/media').status_code,404)
        self.assertEqual(self.client.post('/v1/videos/unknown/analyze',json={}).status_code,403)

    @unittest.skipUnless((server.ROOT/'private-data/retailaction/manifest.json').is_file(),'Original video subset not installed')
    def test_original_video_ranges_analysis_and_export(self):
        import shutil
        shutil.copytree(server.ROOT/'private-data/retailaction',server.DATA/'retailaction')
        source=self.client.get('/v1/videos').json()
        self.assertTrue(source['available'])
        entry=source['videos'][0]
        response=self.client.get('/v1/videos/'+entry['id']+'/media',headers={'Range':'bytes=0-99'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.content),100)
        expected=(server.DATA/'retailaction'/entry['path']).read_bytes()[:100]
        self.assertEqual(response.content,expected)
        analysis=self.client.get('/v1/videos/'+entry['id']+'/analysis')
        self.assertEqual(analysis.status_code,200)
        self.assertEqual(analysis.json()['source_sha256'],entry['sha256'])
        exported=self.client.get('/v1/videos/'+entry['id']+'/export')
        self.assertEqual(exported.json(),analysis.json())
        self.assertEqual(self.client.get('/v1/videos/unknown/media').status_code,404)
        self.assertEqual(self.client.post('/v1/videos/unknown/analyze',json={},headers=self.headers).status_code,404)

    @unittest.skipUnless((server.ROOT/'private-data/rpc/manifest.json').exists(), 'Original RPC subset not installed')
    def test_real_perception_queue_is_separate_and_idempotent(self):
        import shutil
        target=server.DATA/'rpc'
        target.mkdir()
        shutil.copyfile(server.ROOT/'private-data/rpc/manifest.json',target/'manifest.json')
        request={'model':'foreground-components-v1','idempotency_key':'real-rpc'}
        first=self.client.post('/v1/perception/runs',json=request,headers=self.headers)
        self.assertEqual(first.status_code,202,first.text)
        again=self.client.post('/v1/perception/runs',json=request,headers=self.headers)
        self.assertEqual(first.json(),again.json())
        conflict=self.client.post('/v1/perception/runs',json={**request,'model':'watershed-v1'},headers=self.headers)
        self.assertEqual(conflict.status_code,409)
        self.assertEqual(self.client.get('/v1/state').json()['runs'],[])
        self.assertEqual(len(self.client.get('/v1/perception').json()['runs']),1)
        identifier=first.json()['id']
        self.client.post('/v1/runs/'+identifier+'/cancel',json={},headers=self.headers)
        server.execute_run(server.run_record(identifier))
        self.assertEqual(server.run_record(identifier)['status'],'canceled')

    def test_api_docs_work_without_external_assets(self):
        response=self.client.get('/docs')
        self.assertEqual(response.status_code,200)
        self.assertIn('API contracts',response.text)
        self.assertNotIn('cdn.jsdelivr',response.text)

    def test_duplicate_json_fields_rejected(self):
        response=self.client.post('/v1/suites',content=b'{"name":"a","name":"b"}',headers={**self.headers,'Content-Type':'application/json'})
        self.assertEqual(response.status_code,422)

    def test_cross_origin_and_rebinding_blocked(self):
        self.assertEqual(self.client.post('/v1/suites',json={}).status_code,403)
        self.assertEqual(self.client.post('/v1/suites',json={},headers={**self.headers,'Origin':'https://example.com'}).status_code,403)
        self.assertEqual(self.client.get('/v1/state',headers={'Host':'attacker.example'}).status_code,400)

    def test_bad_video_rejected_and_removed(self):
        response=self.client.post('/v1/assets',content=b'not a video',headers={**self.headers,'Content-Type':'video/mp4'})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(list((server.DATA/'media').iterdir()),[])

    def test_csv_validation_does_not_register_evidence(self):
        request={'format':'csv','content':'id,type,t_ms,sku,quantity\nscan,scan_add,100,item,1\npaid,payment_complete,200,,',
                 'inputs':{'catalog':{'0':'item'},'offset_ms':50,'bagging_x':.6,'min_observations':3}}
        response=self.client.post('/v1/scan-logs/validate',json=request,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['payment_video_ms'],250)
        self.assertEqual(response.json()['net_scan_counts'],{'item':1})
        self.assertEqual(self.client.get('/v1/state').json()['cases'],[])
        malformed={**request,'content':'id,type,t_ms\npaid,payment_complete,0.2'}
        self.assertEqual(self.client.post('/v1/scan-logs/validate',json=malformed,headers=self.headers).status_code,422)

    def test_prediction_run_and_export_reproduce(self):
        frozen=self.register()
        response=self.client.post('/v1/runs',json={'suite_id':frozen['id'],'idempotency_key':'first','imported':bundle(frozen['suite'])},headers=self.headers)
        self.assertEqual(response.status_code,202,response.text)
        identifier=response.json()['id']
        server.execute_run(server.run_record(identifier))
        run=self.client.get('/v1/runs/'+identifier).json()
        self.assertEqual(run['status'],'completed')
        self.assertFalse(run['result']['execution']['inference_executed'])
        archive=self.client.get('/v1/runs/'+identifier+'/export')
        self.assertEqual(archive.status_code,200)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            report=json.loads(zipped.read('report.json'))
            self.assertEqual(report,server.score(json.loads(zipped.read('suite.json')),json.loads(zipped.read('predictions.json'))))
            self.assertNotIn('video.mp4',zipped.namelist())

    def test_idempotency_and_cancellation(self):
        frozen=self.register();request={'suite_id':frozen['id'],'idempotency_key':'same'}
        first=self.client.post('/v1/runs',json=request,headers=self.headers).json()
        second=self.client.post('/v1/runs',json=request,headers=self.headers).json()
        self.assertEqual(first,second)
        changed={**request,'imported':bundle(frozen['suite'])}
        self.assertEqual(self.client.post('/v1/runs',json=changed,headers=self.headers).status_code,409)
        identifier=first['id']
        self.assertEqual(self.client.post('/v1/runs/'+identifier+'/cancel',headers=self.headers).json()['status'],'canceled')
        server.execute_run(server.run_record(identifier))
        self.assertEqual(server.run_record(identifier)['status'],'canceled')

    def test_restart_queues_interrupted_work(self):
        frozen=self.register()
        identifier=self.client.post('/v1/runs',json={'suite_id':frozen['id'],'idempotency_key':'restart'},headers=self.headers).json()['id']
        server.update_run(identifier,status='running',attempts=1)
        server.initialize()
        self.assertEqual(server.run_record(identifier)['status'],'queued')

    def test_missing_media_is_partial_not_success(self):
        frozen=self.register()
        identifier=self.client.post('/v1/runs',json={'suite_id':frozen['id'],'idempotency_key':'missing'},headers=self.headers).json()['id']
        server.execute_run(server.run_record(identifier))
        result=server.run_record(identifier)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['result']['report']['metrics']['processing_coverage']['numerator'],0)
        self.assertIn('case',result['result']['failures'])

    def test_immutable_case_id(self):
        self.register()
        request={'asset_id':'asset','title':'Correction','annotation':case(),'inputs':inputs()}
        self.assertEqual(self.client.post('/v1/cases',json=request,headers=self.headers).status_code,409)

    def test_private_media_path_is_not_user_supplied(self):
        self.assertEqual(self.client.get('/v1/media/does-not-exist').status_code,404)
        self.assertNotEqual(self.client.get('/v1/media/..%2Fworkbench.sqlite').status_code,200)


if __name__ == '__main__':unittest.main()
