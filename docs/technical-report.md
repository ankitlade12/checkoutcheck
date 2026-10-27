# CheckoutCheck: inspectable evidence for checkout vision

**OpenCV AI Competition 2026 · technical report · October 26, 2026**

Repository: https://github.com/ankitlade12/checkoutcheck  
Judge application: https://d2pt18a0j9tuil.cloudfront.net

## Problem, users and intended benefit

Seeing a product, observing a shelf interaction and recording a checkout scan are different measurements. Conflating them can produce unreliable alerts and unnecessary customer interventions. CheckoutCheck gives computer-vision engineers, researchers and retail evaluation teams a workbench to inspect original inputs, compare methods, examine failures, and reproduce scores before considering deployment around customers.

The delivered POC includes real-image benchmarking, an original-video inspection lab, a bounded vision agent, an independently implemented transaction evaluator, reproducible exports, and a public AWS review interface. Its software workflows work; real checkout discrepancy accuracy and customer impact have not been validated. A production MVP requires consented synchronized checkout/POS evidence and independent review.

## Data and implementation

The installation contains 24 original RPC validation photographs with 291 product annotations, 400 disjoint original training photographs covering 200 categories, and six original RetailAction clips with 176 encoded frames. Inputs are acquired separately, checksummed and attributed. The reference annotations enter scoring, not validation-image inference. No generated footage, fabricated scan histories or synthetic image dataset is used.

OpenCV 5 implements decoding, resizing, color conversion, foreground segmentation, morphology, connected components, watershed, SIFT, geometric matching, sharpness/motion diagnostics and marker-instrumented transaction observations. These functions perform substantive application work. PyTorch/torchvision executes the Faster R-CNN network; it is not represented as OpenCV DNN inference. The real-photo fine-tune used 400 original photographs for two epochs without augmentation or compositing. Upstream COCO/ImageNet checkpoint provenance is documented, not independently audited image by image.

The browser client uses HTML/CSS/JavaScript. FastAPI exposes the application API; SQLite holds queue metadata and results. A single worker launches bounded subprocesses, handles cancellation and restart recovery, and commits final results atomically. Suite hashes and idempotency keys bind requests to their evidence/configuration. The transaction evaluator supports imported observations or marker-assisted processing when actual synchronized inputs are supplied; no real checkout dataset was available to validate that path end to end.

## AWS architecture and deployment

See [architecture.md](architecture.md) and the packaged diagram. Personal-account EC2 executed the real application workloads. Private encrypted S3 stores approved source, original inputs and model weights. The worker uses a scoped instance role; CloudWatch records application logs; Session Manager provides private operator access. Credentials are excluded from source and containers.

CloudFront HTTPS now serves a separate read-only application on the EC2 host. Its origin permits CloudFront traffic only and checks a private origin header. The review container has no worker, no writable data mount and a query-only SQLite connection to a consistent snapshot. An API allowlist blocks mutation routes and private transaction media. Comparisons calculate existing scores without changing data. Results and database backups remain on EC2; no generated results are uploaded to S3. Health and browser checks verify the external HTTPS path, not just localhost.

The five baseline measurements and agent run used t3.large; the review host was subsequently resized to t3.small. Its persistent shutdown timer ends hosting on **November 11, 2026 at 00:00 UTC (November 10 at 6 p.m. Central)**. See the [hosting guide](../infra/aws-public-review.md) for deployment, snapshot refresh and shutdown.

SQLite online backup restoration passed an integrity check. Backups remain on the EC2 volume, so deleting that volume also deletes its backups. The first COCO attempt exceeded the original 180-second cap; the bounded worker limit was raised to 600 seconds and both neural workflows subsequently passed.

## Image evaluation and failure cases

One-to-one matching uses IoU ≥ 0.5. The 24-image subset is exploratory, balanced across easy/medium/hard cases, and not an untouched final holdout. Raw exports include image-level predictions, explicit denominators, exclusions, hashes and scoring configuration. These measurements cannot establish population performance.

| AWS method | Matched | False positives | Precision | Recall |
|---|---:|---:|---:|---:|
| Foreground components | 17 | 103 | 14.17% | 5.84% |
| Watershed | 37 | 166 | 18.23% | 12.71% |
| SIFT reference matcher | 48 | 30 | 61.54% | 16.49% |
| COCO detector baseline | 13 | 1 | 92.86% | 4.47% |
| RPC-trained detector | 105 | 36 | 74.47% | 36.08% |
| Adaptive vision agent | 94 | 53 | 63.95% | 32.30% |

The trained detector still misses 186 of 291 products. The agent misses 197 and does not improve detection accuracy. Classical segmentation merges touching objects and splits objects into multiple regions; background similarity loses some products. SIFT is sensitive to orientation, occlusion and the limited reference bank. Neural scores are uncalibrated and do not identify SKU or payment state. Image overlays and per-image tables expose these failures. An earlier cloud detector timeout remains recorded as a failed run rather than being counted as success.

Original RetailAction videos demonstrate real playback, frame seeking and OpenCV diagnostics. They are publisher-anonymized shelf interactions with selected-frame timing, not continuous checkout transactions. Publisher labels are not model predictions. There are no synchronized scan/payment histories or verified discrepancy outcomes in these clips.

## Agentic Vision evidence

The deterministic controller calls OpenCV quality and foreground tools, then selects a neural detector or watershed based on observed density, warnings and sharpness. Each image is limited to three tool calls. Failures retain the initial observation and request human inspection. The trace records observations, decisions, action, errors and timings; no LLM is claimed.

The AWS run completed 24/24 images, chose neural follow-up 18 times and watershed six times, recommended review 17 times, and made 72 tool calls with zero budget violations. No follow-up failures occurred in that run. A separate fault-injection software check verifies recovery using an original photograph; it is not presented as a real-world failure-rate estimate. Low-sharpness and routing branches are policy-tested. Review necessity has no independent ground truth. No transaction is modified or automatically enforced. See [agentic-vision.md](agentic-vision.md) for the workflow, evaluation and reproduction commands.

## COOL evidence

The official Marketplace product `prod-k6u24vxijyzvg`, AMI `ami-033e481a24f94c8cb`, ran on c8g.large in us-east-1. The actual vendor runtime was OpenCV 5.1.0-dev under `/opt/cool`; the stock baseline was OpenCV 5.0.0 (`opencv-python-headless==5.0.0.93`). Both used Python 3.12, NumPy 2.5.1, one OpenCV thread, the same application code and the same original photos on the same instance.

After one warmup, five measured batches gave median foreground times of 0.875441 s stock and 0.847471 s COOL (1.033×), and watershed times of 2.220637 s stock and 2.132659 s COOL (1.041×). Evaluation scores were identical. Disk/decode time is excluded. Small differences, sequential order and differing OpenCV versions limit causal conclusions; no statistical significance or universal speedup is claimed. Raw reports and runtime configuration are downloadable from the judge application. The temporary instance was terminated after direct, checksum-verified preservation on the original EC2 volume. See [cool-evaluation.md](cool-evaluation.md).

## Build, test and reproduce

Dependencies are pinned in `requirements.lock`; the Dockerfile uses CPU-only PyTorch. Follow the README for the local build, original data acquisition and model training. `./run.command` starts the private local application. Infrastructure templates and operations guides document deployment and private access.

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m checkoutcheck.perception --verify-report path/to/exported-report.json
CHECKOUTCHECK_URL=https://d2pt18a0j9tuil.cloudfront.net python3 tests/browser_public_review.py
```

The original-data environment passed 64 software tests covering validation, scoring, lifecycle, acquisition integrity and training provenance. Private AWS browser checks exercised all five image methods, cancellation, reload persistence, overlays, comparisons and exports; each image score was independently recomputed. All six original clips passed playback, seeking, source-time mapping, diagnostics, range requests and export. These checks observed zero JavaScript or HTTP errors.

The package records the exact checks run. Browser verification covers actual stored runs, agent traces, comparisons, original video, mobile layout and blocked public mutations. Source-only CI skips checks whose licensed originals are not installed. Passing software checks is not evidence of real checkout accuracy.

## Responsible use and remaining limitations

Use the prototype for research and review. It must not infer intent, label a person as stealing, or trigger autonomous enforcement. Preserve publisher anonymization and do not reidentify people. Collect consented transaction evidence, document purpose/retention, obtain independent annotations and evaluate unnecessary interventions before any customer-facing trial. Multi-user identity, production authorization, retention controls, operational resilience and independent external validation remain outside this hackathon POC.

Own application code is MIT licensed. RPC material remains CC BY-NC-SA 4.0; RetailAction retains the Standard.AI Dataset License. Copies and notices accompany redistributed material; neither dataset is relicensed as MIT. Organizer submission/reuse terms must be checked against these third-party licenses.

The requested video uses Indian English male computer narration and a product-demo format. An opening team credit identifies Ankit Hemant Lade and Sai Jasti, with matching narration. The 4:11 video contains no live team footage; organizer acceptance of name credits for the team requirement is not confirmed. Award consideration is requested based on the provided evidence; eligibility and judging outcomes are not asserted. Devpost upload/final submission is a separate step and is not implied by preparing this package.

## Community pilot acceptance

The hackathon application is a single-operator workbench with a public read-only review service. Before a community pilot, record independent acceptance evidence for:

- Consented synchronized checkout recordings, actual scan/void/payment events, independently reviewed physical inventory and measured alignment/drift tolerances. Follow the [capture protocol](real-dataset-sources.md#real-transaction-capture-protocol).
- Supported product detection/tracking, calibrated uncertainty and independently frozen held-out evaluation; retain paired source sessions in the same split and report ambiguous/occluded cases.
- Annotation revisions, reviewer disagreements, correction lineage, affected-result notices and rights-filtered reproducible exports.
- Membership/revocation and cross-project isolation, aggregate quotas, interrupted-upload recovery, retention/withdrawal and deletion across derivatives and backups. Accounts remain outside the hackathon scope.
- External onboarding, accessibility, security, load and recovery tests; versioned regression policies that distinguish model regressions, infrastructure failures and insufficient evidence.
- Maintainer ownership, operational costs, contributor/support routes, practitioner feedback and substantiated product claims.

Keep SQLite and the single worker until measured concurrency needs justify migration. Distributed workers would require leases, heartbeats, duplicate-delivery recovery and tested database migrations. For each acceptance gate, retain its artifact, environment, date, reviewer, measured outcome and limitations.
