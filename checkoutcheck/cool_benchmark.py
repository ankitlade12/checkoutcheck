"""Run real CheckoutCheck core workloads in separate COOL and stock environments."""
import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path


def benchmark(directory, distribution, repetitions=5):
    import cv2
    import numpy as np
    from .perception import detect, load_manifest, score_predictions
    if cv2.__version__.split('.')[0] != '5':
        raise ValueError('OpenCV 5 is required')
    if distribution == 'cool' and (platform.machine() not in ('aarch64', 'arm64') or '/opt/cool/' not in str(Path(cv2.__file__).resolve())):
        raise ValueError('COOL evidence requires the official /opt/cool installation on Arm')
    cv2.setNumThreads(1)
    root = Path(directory)
    manifest = load_manifest(root)
    images = []
    for entry in manifest['images']:
        raw = (root/'images'/entry['file_name']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Original image checksum mismatch')
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (entry['height'], entry['width']):
            raise ValueError('Original image dimensions mismatch')
        images.append((entry['id'], image))
    workloads = {}
    for model in ('foreground-components-v1', 'watershed-v1'):
        for _, image in images:
            detect(image, model)
        timings, predictions = [], []
        for repetition in range(repetitions):
            started = time.perf_counter()
            predictions = [{'image_id': identifier, **detect(image, model)} for identifier, image in images]
            timings.append(time.perf_counter()-started)
        workloads[model] = {'warm_batch_seconds': timings, 'median_batch_seconds': statistics.median(timings),
                            'predictions': predictions, 'report': score_predictions(manifest, predictions)}
    return {'distribution': distribution, 'opencv_version': cv2.__version__, 'opencv_module': cv2.__file__,
            'opencv_build_information': cv2.getBuildInformation(), 'machine': platform.machine(),
            'python': platform.python_version(), 'numpy': np.__version__, 'threads': cv2.getNumThreads(),
            'dataset_hash': manifest['hash'], 'images': len(images), 'repetitions': repetitions,
            'source_sha256': hashlib.sha256(Path(__file__).with_name('perception.py').read_bytes()).hexdigest(),
            'timing_scope': 'Decoded original images; full application detect() pipeline; excludes disk and decode; one warmup batch',
            'workloads': workloads}


def compare(baseline, candidate):
    for field in ('dataset_hash', 'source_sha256', 'machine', 'threads', 'repetitions', 'images', 'numpy'):
        if baseline[field] != candidate[field]:
            raise ValueError('Benchmark conditions differ: '+field)
    if baseline['distribution'] != 'stock' or candidate['distribution'] != 'cool':
        raise ValueError('Expected stock baseline and official COOL candidate')
    return {model: {'stock_seconds': baseline['workloads'][model]['median_batch_seconds'],
                    'cool_seconds': candidate['workloads'][model]['median_batch_seconds'],
                    'speedup': baseline['workloads'][model]['median_batch_seconds']/candidate['workloads'][model]['median_batch_seconds'],
                    'metrics_equal': baseline['workloads'][model]['report']==candidate['workloads'][model]['report']}
            for model in baseline['workloads']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='private-data/rpc')
    parser.add_argument('--distribution', choices=['stock', 'cool'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--compare', nargs=2, metavar=('STOCK_JSON', 'COOL_JSON'))
    args = parser.parse_args()
    if args.compare:
        result = compare(*(json.loads(Path(path).read_text()) for path in args.compare))
    elif args.distribution:
        result = benchmark(args.directory, args.distribution)
    else:
        parser.error('--distribution or --compare is required')
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
