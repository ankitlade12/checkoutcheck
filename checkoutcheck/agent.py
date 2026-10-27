"""Bounded, deterministic vision agent; no reference labels enter its decisions."""
import hashlib
import time
from pathlib import Path

POLICY = {'version': 'vision-investigator/1.0', 'maximum_tool_calls': 3,
          'minimum_sharpness': 20.0, 'dense_foreground_fraction': 0.5,
          'count_disagreement_for_review': 2}


def choose_tool(sharpness, foreground_fraction, warnings):
    if sharpness < POLICY['minimum_sharpness']:
        return 'request_human_review', 'Image sharpness is below the declared supported threshold'
    if warnings or foreground_fraction >= POLICY['dense_foreground_fraction']:
        return 'rpc_neural_detector', 'Observed foreground density or background warning requires another detector'
    return 'watershed_refinement', 'Observed foreground permits a cheaper touching-region refinement'


class VisionAgent:
    def __init__(self, root):
        self.root = Path(root)
        self.neural = None
        self.provenance = {'policy': POLICY, 'controller': 'deterministic bounded tool selection',
                           'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'reference_annotations_available_to_controller': False}

    def detect(self, image):
        import cv2
        from .perception import detect
        trace = []

        def tool(name, call):
            if len(trace) >= POLICY['maximum_tool_calls']:
                raise ValueError('Agent tool budget exhausted')
            started = time.monotonic()
            item = {'step': len(trace)+1, 'tool': name, 'status': 'running'}
            trace.append(item)
            try:
                value = call()
                item['status'] = 'completed'
                return value
            except Exception as error:
                item.update(status='failed', error=str(error))
                raise
            finally:
                item['runtime_seconds'] = time.monotonic()-started

        quality = tool('opencv_quality', lambda: float(cv2.Laplacian(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()))
        trace[-1]['observation'] = {'laplacian_variance': quality}
        initial = tool('opencv_foreground', lambda: detect(image, 'foreground-components-v1'))
        trace[-1]['observation'] = {'count': len(initial['boxes']),
                                  'foreground_fraction': initial['foreground_fraction'],
                                  'warnings': initial['warnings']}
        selected, reason = choose_tool(quality, initial['foreground_fraction'], initial['warnings'])
        trace[-1]['next_action'] = {'tool': selected, 'reason': reason}
        result = initial
        error = None
        if selected != 'request_human_review':
            try:
                if selected == 'rpc_neural_detector':
                    def neural_call():
                        if self.neural is None:
                            from .learned_detector import LearnedDetector
                            self.neural = LearnedDetector(self.root, fine_tuned=True)
                        return self.neural.detect(image)
                    result = tool(selected, neural_call)
                    self.provenance['neural_model'] = self.neural.provenance
                else:
                    result = tool(selected, lambda: detect(image, 'watershed-v1'))
                trace[-1]['observation'] = {'count': len(result['boxes']), 'warnings': result['warnings']}
            except (OSError, ValueError, RuntimeError, cv2.error) as failure:
                error = str(failure)
                result = initial
        disagreement = abs(len(initial['boxes'])-len(result['boxes']))
        review = selected == 'request_human_review' or error is not None or disagreement >= POLICY['count_disagreement_for_review']
        return {**result, 'agent_trace': trace,
                'agent_decision': {'selected_tool': selected, 'reason': reason,
                                   'human_review_recommended': review,
                                   'count_disagreement': disagreement, 'tool_error': error,
                                   'status': 'human_review_requested' if review else 'prediction_ready_for_inspection',
                                   'automatic_transaction_action': False}}


def summarize(predictions):
    routes = {}
    for item in predictions:
        route = item['agent_decision']['selected_tool']
        routes[route] = routes.get(route, 0)+1
    return {'policy': POLICY, 'images': len(predictions), 'routes': routes,
            'human_review_requests': sum(p['agent_decision']['human_review_recommended'] for p in predictions),
            'failed_followup_tools': sum(p['agent_decision']['tool_error'] is not None for p in predictions),
            'tool_calls': sum(len(p['agent_trace']) for p in predictions),
            'budget_violations': sum(len(p['agent_trace'])>POLICY['maximum_tool_calls'] for p in predictions),
            'note': 'Routing is experimental and deterministic; task completion does not certify prediction correctness.'}
