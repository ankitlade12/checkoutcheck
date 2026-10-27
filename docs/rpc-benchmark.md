# Original RPC photograph benchmark

Measured locally on October 26, 2026. This document retains the macOS image results; see [AWS verification](technical-report.md#image-evaluation-and-failure-cases) for separately measured Linux execution. Neither experiment establishes real transaction accuracy.

## Source and selection

[RPC authors' project](https://rpc-dataset.github.io/) and [author-linked Kaggle distribution](https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset). Attribution: Xiu-Shen Wei, Quan Cui, Lei Yang, Peng Wang, Lingqiao Liu, Jian Yang, *RPC: A Large-Scale and Fine-Grained Retail Product Checkout Dataset*. License: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). This installation is for local noncommercial research; commercial deployment is not cleared.

- 24 original validation photographs: eight each from the publisher's easy, medium and hard levels; 291 annotated product instances.
- 400 original training photographs: two per each of 200 categories. Only their training annotations define reference crops.
- Stable SHA-256 filename ranking with seed `checkoutcheck-rpc-v1`. Selection is independent of measured performance. The small validation sample is exploratory, not a final holdout or full RPC benchmark result.
- No rendered images, pasted products, generated scan logs, invented labels or synthetic training data. Resizing, grayscale conversion and cropping of original training photographs occur inside feature extraction.
- Original annotation files, image checksums, selection parameters, source/license, manifest hashes and acquisition receipt are retained under `private-data/rpc/`. This directory is excluded from source control.

Validation manifest: `77d5cd0bbf7510fb14bb7debbddc56c0a2766093800650fc7f8c3ae097a17a0f`.

Training reference manifest: `9063747ed62bc709badf7285d3f0561b4f5d67d39e1b3d9278c488fa5a93b399`.

## Actual initial measurements

All three methods scored all 24 photographs using OpenCV 5.0.0. A localization match requires one-to-one box intersection-over-union ≥ 0.5. Maximum bipartite matching prevents double credit. Metrics are micro-aggregated across scored images; missing predictions are excluded with reduced coverage, never treated as successful empty observations.

| Method | Matched / 291 | False positives | Precision | Recall | Count MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Foreground components | 17 | 103 | 14.17% | 5.84% | 7.46 |
| Distance watershed | 37 | 167 | 18.14% | 12.71% | 7.21 |
| Real-reference SIFT | 44 | 25 | 63.77% | 15.12% | 9.25 |

SIFT also matched the correct SKU and location for 31 objects: SKU precision 44.93%, SKU recall 10.65%. It emitted 69 boxes. Its better localization precision comes with substantial undercounting; it is not the best method on every metric. No method is suitable for production product counting. No confidence calibration or statistical population claim is made.

## Photo-trained neural detector

The application now also runs Faster R-CNN MobileNetV3 FPN, first with official COCO weights and then fine-tuned for product/background localization on the 400 original RPC training photographs. The evaluation images are excluded from training. Both full epochs visit all 400 training photographs; no rendered/composited data, flipping or other augmentation is used in our fine-tuning. OpenCV decodes and converts the real images; PyTorch executes the neural detector. Do not describe the neural network itself as an OpenCV DNN model.

| Method | Matched / 291 | False positives | Precision | Recall | Count MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Official COCO checkpoint | 13 | 1 | 92.86% | 4.47% | 11.54 |
| Real RPC fine-tune, two epochs | 105 | 36 | 74.47% | 36.08% | 6.25 |

These are additional exploratory measurements on the same fixed 24 photographs, not independent holdout claims. The fine-tuned method improves recall over SIFT but still misses 186 objects. It has no SKU head, no calibrated uncertainty, and no scan/payment inference. A stronger detection architecture alone did not help: the unadapted COCO checkpoint missed nearly everything. The real training step matters.

Provenance follows the [official torchvision model definition](https://github.com/pytorch/vision/blob/main/torchvision/models/detection/faster_rcnn.py) and [published training recipe](https://github.com/pytorch/vision/tree/main/references/detection#faster-r-cnn-mobilenetv3-large-fpn). The upstream recipe uses COCO photographs, an ImageNet-initialized backbone and horizontal flips; it does not specify synthetic retail renders or copy/paste for this checkpoint. This is documentation-based provenance, not an independent audit of all upstream training images. Original RPC source checksums, source split, seed, optimizer, every training filename/hash, epochs, loss history, package versions and model checksum are saved in `private-data/models/rpc-fasterrcnn-v1/manifest.json`.

Install the pinned environment and reproduce the model in a fresh data directory:

```sh
.venv/bin/python -m checkoutcheck.learned_detector --prepare-base
.venv/bin/python -m checkoutcheck.learned_detector --epochs 2
.venv/bin/python -m checkoutcheck.perception --model fasterrcnn-coco-v1 --output artifacts/rpc-fasterrcnn-coco.json
.venv/bin/python -m checkoutcheck.perception --model fasterrcnn-rpc-v1 --output artifacts/rpc-fasterrcnn-trained.json
```

Training refuses to overwrite an existing registered model. Inference verifies its weights and manifest and performs no automatic download. The model remains subject to the real-data noncommercial constraints; no commercial clearance is claimed.

SIFT uses feature matching, a ratio test, RANSAC homographies and nonmaximum suppression. It builds its bank from training images only. Validation annotations are passed to the evaluator after inference, not to the detector. Parameters and adapter source/build hashes are recorded per run. The first two methods are class agnostic and their SKU metrics are unavailable, not zero.

## Reproduce

From the project root with the pinned environment installed:

```sh
.venv/bin/python -m checkoutcheck.rpc --count 24 --references 2
mkdir -p artifacts
.venv/bin/python -m checkoutcheck.perception --model foreground-components-v1 --output artifacts/rpc-components.json
.venv/bin/python -m checkoutcheck.perception --model watershed-v1 --output artifacts/rpc-watershed.json
.venv/bin/python -m checkoutcheck.perception --model sift-reference-v1 --output artifacts/rpc-sift.json
.venv/bin/python -m checkoutcheck.perception --verify-report artifacts/rpc-sift.json
./run.command
```

Open `http://127.0.0.1:8765/#perception` and use **Run on all 24 images** to persist jobs in the application. CLI output alone does not insert an application run. The worker enforces a 600-second process limit, supports cancellation, and retains results in SQLite. No cloud resources or credentials are required.

The JSON export includes original annotation metadata, predictions, scoring, configuration, failures and provenance. `--verify-report` recomputes scoring exactly; it does not rerun inference or independently authenticate the publisher. Rerunning inference additionally requires the original hash-matched photos and the pinned OpenCV environment. The desktop browser export has its own end-to-end verification check.

## Application/API

- `GET /v1/perception`: registered dataset, reference bank, methods, run states.
- `POST /v1/perception/runs`: allowed `model` and unique `idempotency_key`.
- `GET /v1/perception/images/{image_id}`: registered checksum-verified original JPEG only.
- Existing run detail, cancellation and export endpoints also support perception jobs.
- `POST /v1/perception/comparisons`: `baseline` and `candidate` run IDs; dataset, evaluator and IoU must agree.

All mutations retain the local same-origin boundary. Image metrics and runs are separate from transaction metrics and suites. Blue replay boxes are publisher annotations; orange boxes are actual model predictions. Both can be toggled independently.

## Remaining evidence

The next model-development step is a stronger detector with documented real-only training provenance, then a separately frozen evaluation set. The next transaction step is consented checkout video synchronized with actual scan events and independent physical inventory labels. RPC images provide neither payment truth nor intervention outcomes, so they cannot establish discrepancy recall, shopper fairness, or reduced false interventions. Private AWS execution and evidence packaging are verified. Collaborative review, real transaction validation and final submission remain open; see the [technical report](technical-report.md#community-pilot-acceptance).
