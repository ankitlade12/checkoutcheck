# Implementation and verification status

Updated October 26, 2026. This is the current status record; the [roadmap](roadmap.md) describes future acceptance requirements.

## Verified hackathon POC

| Area | Implemented and checked | Practical limit |
| --- | --- | --- |
| Image perception | Five methods; 24 original RPC validation photos; overlays, comparison, exports and exact score recomputation | Exploratory subset; best detector recall 36.08%, no neural SKU head |
| Original videos | Six RetailAction clips, 176 frames; playback, source-time mapping, seeking, diagnostics and exports | Shelf interactions with publisher labels; no POS/payment truth |
| Job lifecycle | SQLite queue, idempotency, persistence, bounded subprocesses, cancellation and restart retry | One operator and worker; no distributed leases |
| Transaction software | MP4 validation, recorded JSON/CSV scan-log validation, immutable suites, marker adapter, imported predictions, event replay and deterministic scoring | Software tests pass; real synchronized checkout capture is unavailable |
| Local application | Navigation, intake, image/video workflows and mobile layout; no JavaScript errors in verified browser runs | No application login or tenant isolation |
| AWS execution | CPU-only EC2, scoped instance role, private encrypted inputs, CloudWatch logs, SSM tunnel; all five methods and six video workflows checked | Private demonstration; compute stopped after verification |
| Recovery | Online SQLite snapshot restored into an isolated database; integrity check passed | Cloud backup remains on EC2 only by operator choice; deleting its volume deletes that backup |
| Packaging | Source/evidence archive, technical report, diagram, checksums and actual local/AWS walkthroughs | Generated artifacts remain private and are absent from Git |

## Verification evidence

- **56 tests passed** in the original-data environment, covering evaluator arithmetic, validation, API behavior, lifecycle, acquisition integrity and training provenance.
- Source-only GitHub CI intentionally skips real-data checks when licensed originals or model weights are absent. Passing CI alone does not establish model quality.
- AWS browser checks exercised all five methods, cancellation, reload persistence, image overlays, comparisons and report export. Each successful image score was independently recomputed.
- Video checks covered all six original clips, frame/source-time seeking, fresh diagnostics, HTTP range requests, export and mobile layout, with zero JavaScript or HTTP failures.
- The first AWS COCO attempt hit the original 180-second worker cap. A bounded 600-second limit was deployed; both neural workflows then passed. The failed attempt remains in the private run history.
- SQLite restoration preserved five completed image runs, one canceled run and the failed attempt, with zero transaction cases.

[Image benchmark and provenance](rpc-benchmark.md) · [AWS measurements](aws-verification.md) · [Data sources](real-dataset-sources.md)

## Remaining acceptance gates

1. Real checkout video with synchronized recorded scan events, independently reviewed physical outcomes and permitted use.
2. Supported-product detector/tracker validation, calibration and held-out evaluation beyond this small image sample.
3. Independent review, correction lineage, retention/withdrawal and cross-user isolation before a community pilot.
4. Independent user reproduction and usability/accessibility testing; multi-user load and failure testing before scaling.
5. Human team introduction, final reviewed video, judge access and competition submission.

No transaction accuracy, shopper-impact improvement, novelty, award eligibility or full community-MVP completion is claimed. Application accounts remain outside the private hackathon scope.
