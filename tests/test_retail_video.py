"""Checks original publisher clips; creates no video or transaction fixtures."""
import json
import unittest
from pathlib import Path

from checkoutcheck.retail_video import analyze, load_manifest

ROOT=Path(__file__).resolve().parents[1]/'private-data'


@unittest.skipUnless((ROOT/'retailaction/manifest.json').is_file(),'Original RetailAction videos not installed')
class OriginalVideoTests(unittest.TestCase):
    def test_every_original_frame_maps_to_publisher_time(self):
        manifest=load_manifest(ROOT/'retailaction')
        for video in manifest['videos']:
            result=analyze(ROOT/'retailaction',video['id'])
            self.assertEqual(result['source_sha256'],video['sha256'])
            self.assertTrue(result['frames'])
            times=[f['source_seconds'] for f in result['frames']]
            self.assertEqual(times,sorted(times))
            self.assertTrue(all(0<=t<=result['source_duration_seconds'] for t in times))
            self.assertIsNone(result['frames'][0]['changed_pixel_fraction'])
            self.assertTrue(all(0<=f['changed_pixel_fraction']<=1 for f in result['frames'][1:]))
            self.assertNotIn('transaction_truth',result)
            self.assertNotIn('scan_events',result)

    def test_unregistered_video_rejected(self):
        with self.assertRaises(ValueError):analyze(ROOT/'retailaction','../../outside')


@unittest.skipUnless((ROOT/'models/rpc-fasterrcnn-v1/manifest.json').is_file(),'Fine-tuned model not installed')
class TrainingProvenanceTests(unittest.TestCase):
    def test_training_and_evaluation_photographs_are_disjoint(self):
        model=json.loads((ROOT/'models/rpc-fasterrcnn-v1/manifest.json').read_text())
        validation=json.loads((ROOT/'rpc/manifest.json').read_text())
        references=json.loads((ROOT/'rpc/references/manifest.json').read_text())
        self.assertEqual(model['training_manifest_hash'],references['hash'])
        self.assertEqual(model['training_source_split'],'train2019')
        self.assertFalse(model['evaluation_images_used_for_training'])
        self.assertEqual(model['training_images'],len(references['images']))
        self.assertFalse({i['sha256'] for i in model['training_sources']} & {i['sha256'] for i in validation['images']})
        self.assertTrue(all(e['images']==len(references['images']) for e in model['history']))
