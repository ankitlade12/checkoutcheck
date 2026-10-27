# COOL execution evidence

The official AWS Marketplace **Cloud Optimized OpenCV For AWS Graviton4** product executed CheckoutCheck's actual foreground-components and watershed pipelines on October 26, 2026. These are the same `detect()` functions used by the application and agent, not an unrelated microbenchmark. The temporary benchmark instance was terminated after its reports were copied directly to the persistent project EC2 volume and checksums verified. Generated reports were not uploaded to S3.

## Runtime and method

| Configuration | Value |
|---|---|
| Official product | `prod-k6u24vxijyzvg` |
| Marketplace AMI | `ami-033e481a24f94c8cb` |
| Region / instance | us-east-1 / c8g.large, AWS Graviton4, aarch64 |
| COOL runtime | OpenCV **5.1.0-dev**, vendor `/opt/cool` installation |
| Stock baseline | `opencv-python-headless==5.0.0.93` (OpenCV 5.0.0) |
| Shared Python / NumPy | Python 3.12 / NumPy 2.5.1 |
| OpenCV threads | 1 |
| Inputs | Existing 24 original RPC validation photos, checksummed |
| Timing | One warmup batch; five measured batches per pipeline; median |

The vendor listing calls its current release 3.1; the AMI name is `Graviton5-COOL-v3-prod-k6u24vxijyzvg`, despite belonging to the Graviton4 listing. We report the actual loaded runtime and instance rather than inferring versions or hardware from that name. The loaded module was `/opt/cool/python_3.12/site-packages/cv2/python-3.12/cv2.cpython-312-aarch64-linux-gnu.so`. Raw reports include the complete OpenCV build configuration and source/dataset hashes.

## Observed results

| Actual application workload | Stock median / 24 images | COOL median / 24 images | Stock ÷ COOL | Evaluation scores |
|---|---:|---:|---:|---|
| Foreground components | 0.875441 s | 0.847471 s | 1.033× | Identical |
| Watershed | 2.220637 s | 2.132659 s | 1.041× | Identical |

These are small observed timing differences from one machine and one small subset. Runs were sequential, with stock first and COOL second. Runtime versions differ. Disk I/O and image decoding are excluded. This experiment does not establish a general speedup, isolate the effect of COOL optimizations from version changes, or measure complete web-request latency. No statistical significance claim is made.

## Reproduce

Subscribe to the [official COOL listing](https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs), launch its Arm AMI, install this repository and acquire the same original RPC subset. Keep the stock environment separate: do not pip-install OpenCV over the vendor build.

```sh
python3.12 -m venv /opt/checkoutcheck/stock
/opt/checkoutcheck/stock/bin/pip install numpy==2.5.1 opencv-python-headless==5.0.0.93
/opt/checkoutcheck/stock/bin/python -m checkoutcheck.cool_benchmark \
  --directory /opt/checkoutcheck/data/rpc --distribution stock --output stock.json

# Activation sets vendor library paths; calling the Python binary alone is insufficient.
source /opt/cool/venvs/python_3.12/bin/activate
python -m checkoutcheck.cool_benchmark \
  --directory /opt/checkoutcheck/data/rpc --distribution cool --output cool.json
python -m checkoutcheck.cool_benchmark --compare stock.json cool.json --output comparison.json
```

The command refuses non-OpenCV-5 environments and refuses to label a run COOL unless the loaded module is under `/opt/cool` on Arm. The comparison checks that dataset hash, application source hash, architecture, threads, repetition count, image count and NumPy match. AWS instance configuration supplies the additional same-machine evidence.

## Inspect evidence

Open **Real-data lab → COOL on AWS Graviton** in the [judge application](https://d2pt18a0j9tuil.cloudfront.net). Its stock, COOL, comparison and deployment download links serve the preserved reports directly from EC2.

| Report | SHA-256 |
|---|---|
| stock.json | `1a4beedf05d889f1b097a4260fe618560bfa943bed20d296caf6b6aa9dac010c` |
| cool.json | `786f9aa44d5618c94f13589ce532acf872d0ee2de515d690688cd06f36823d85` |
| comparison.json | `df52f2852cb35c365b70e98694c1eb223eb1e2d23c38822bd616dbde3f1542b1` |
