"""Policy and failure handling checks; images are original RPC photos only."""
import unittest
from pathlib import Path
from unittest.mock import patch

from checkoutcheck.agent import VisionAgent, choose_tool

ROOT = Path(__file__).resolve().parents[1] / 'private-data'


class AgentPolicyTests(unittest.TestCase):
    def test_observations_change_next_action(self):
        self.assertEqual(choose_tool(10, .2, [])[0], 'request_human_review')
        self.assertEqual(choose_tool(30, .2, [])[0], 'watershed_refinement')
        self.assertEqual(choose_tool(30, .6, [])[0], 'rpc_neural_detector')
        self.assertEqual(choose_tool(30, .2, ['background'])[0], 'rpc_neural_detector')

    @unittest.skipUnless((ROOT/'rpc/manifest.json').exists(), 'Original RPC photos not installed')
    def test_failed_followup_retains_observation_and_requests_review(self):
        import cv2
        from checkoutcheck.perception import load_manifest, detect
        entry = load_manifest(ROOT/'rpc')['images'][0]
        image = cv2.imread(str(ROOT/'rpc/images'/entry['file_name']))
        initial = detect(image, 'foreground-components-v1')
        # Deliberate tool exception tests recovery; never exported as evaluation evidence.
        with patch('checkoutcheck.agent.choose_tool', return_value=('watershed_refinement', 'failure injection')), patch(
                'checkoutcheck.perception.detect', side_effect=[initial, RuntimeError('tool unavailable')]):
            result = VisionAgent(ROOT).detect(image)
        self.assertEqual(result['boxes'], initial['boxes'])
        self.assertTrue(result['agent_decision']['human_review_recommended'])
        self.assertFalse(result['agent_decision']['automatic_transaction_action'])
        self.assertEqual(len(result['agent_trace']), 3)
        self.assertEqual(result['agent_trace'][-1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
