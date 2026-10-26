"""Scoring arithmetic and original-data integrity; never creates image datasets."""
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from checkoutcheck.evaluator import digest
from checkoutcheck.perception import load_manifest, match_boxes, score_predictions, verify_result
from checkoutcheck.rpc import select_images, unpack_download

ROOT = Path(__file__).resolve().parents[1] / 'private-data' / 'rpc'


class MatchingTests(unittest.TestCase):
    def test_one_to_one_matching(self):
        box = [0, 0, 10, 10]
        self.assertEqual(len(match_boxes([box, box], [box], .5)), 1)

    def test_identity_and_location_are_both_required(self):
        box = [0, 0, 10, 10]
        self.assertEqual(match_boxes([box], [box], .5, [1], [2]), [])
        self.assertEqual(len(match_boxes([box], [box], .5, [1], [1])), 1)

    def test_maximum_matching_can_reassign_first_match(self):
        matches = match_boxes([[2, 0, 10, 10], [0, 0, 10, 10]],
                              [[0, 0, 10, 10], [4, 0, 10, 10]], .6)
        self.assertEqual(len(matches), 2)

    def test_download_archive_limits_and_member_identity(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('expected.json', '{}')
        self.assertEqual(unpack_download(buffer.getvalue(), 'expected.json', 100), b'{}')
        with self.assertRaises(ValueError):
            unpack_download(buffer.getvalue(), 'other.json', 100)
        with self.assertRaises(ValueError):
            unpack_download(buffer.getvalue(), 'expected.json', 1)


@unittest.skipUnless((ROOT / 'manifest.json').exists(), 'Install original RPC photos to run source integrity checks')
class OriginalDataTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(ROOT)

    def test_missing_predictions_are_excluded_not_zero_error(self):
        report = score_predictions(self.manifest, [])
        self.assertEqual(report['metrics']['scored_images'], 0)
        self.assertEqual(report['metrics']['excluded_images'], len(self.manifest['images']))
        self.assertIsNone(report['metrics']['recall'])
        self.assertIsNone(report['metrics']['count_mae'])

    def test_empty_observation_has_misses_and_zero_sku_recall(self):
        entry = self.manifest['images'][0]
        report = score_predictions(self.manifest, [{'image_id': entry['id'], 'boxes': [], 'category_ids': []}])
        self.assertEqual(report['metrics']['false_negative'], len(entry['annotations']))
        self.assertEqual(report['metrics']['sku_recall'], 0)
        self.assertEqual(report['metrics']['scored_images'], 1)

    def test_duplicate_predictions_and_unknown_categories_rejected(self):
        entry = self.manifest['images'][0]
        prediction = {'image_id': entry['id'], 'boxes': []}
        with self.assertRaises(ValueError):
            score_predictions(self.manifest, [prediction, prediction])
        with self.assertRaises(ValueError):
            score_predictions(self.manifest, [{'image_id': entry['id'], 'boxes': [[0,0,1,1]], 'category_ids': [-1]}])

    def test_export_recomputes_and_detects_changes(self):
        result = {'manifest': self.manifest, 'predictions': [], 'report': score_predictions(self.manifest, [])}
        verify_result(result)
        changed = copy.deepcopy(result)
        changed['report']['metrics']['scored_images'] = 1
        with self.assertRaises(ValueError):
            verify_result(changed)
        changed = copy.deepcopy(result)
        changed['manifest']['images'][0]['sha256'] = 'changed'
        with self.assertRaises(ValueError):
            verify_result(changed)

    def test_manifest_filename_cannot_escape_image_folder(self):
        changed = copy.deepcopy(self.manifest)
        changed['images'][0]['file_name'] = '../outside.jpg'
        changed['hash'] = digest({k:v for k,v in changed.items() if k != 'hash'})
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, 'manifest.json').write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                load_manifest(temporary)

    def test_selection_is_independent_of_input_order(self):
        images = self.manifest['images']
        a = select_images(images, len(images), 'check')
        b = select_images(list(reversed(images)), len(images), 'check')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
