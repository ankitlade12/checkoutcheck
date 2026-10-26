# Input and output contracts

These are format definitions, not a sample dataset. The application starts with no records.

## Inference inputs

| Field | Type and meaning |
| --- | --- |
| `catalog` | Object mapping marker ID strings `0`–`49` to SKU strings. Each physical instance needs a distinct marker. Multiple instances may share a SKU. |
| `events` | Ordered JSON array of mock POS events. |
| `offset_ms` | Integer; video time = POS time + offset. Between -60000 and 60000. |
| `bagging_x` | Number 0.1–0.9; normalized horizontal boundary; bagging is to its right. |
| `min_observations` | Integer 1–30; minimum detection support; UI default 3. Not calibrated on real data yet. |

Every POS event requires `id`, `type`, and nonnegative integer `t_ms`. Supported types:

| Type | Additional fields | Semantics |
| --- | --- | --- |
| `scan_add` | `sku`, integer `quantity` 1–50 | Add a scan to the transaction. |
| `scan_void` | `scan_id` | Void the entire referenced, non-voided scan. Partial quantity voids are not supported. |
| `payment_complete` | None | Final event in a complete stream. |

An incomplete/canceled transaction must not be scored as a completed checkout. The current inference adapter rejects incomplete streams at ingestion instead of storing them as challenge cases; this is a known PRD deviation.

## Reference annotation

Required fields: `id`, `family_id`, `session_id`, `split`, `truth`, `visibility`, `review_status`, `rights_valid`, `input_valid`, `requires_abstention`, and `discrepancies`. Optional `pair_id` denotes a two-case matched pair.

- `split`: `development`, `calibration`, or `holdout`.
- `truth`: `balanced`, `discrepancy`, or `unresolved`.
- `visibility`: `sufficient`, `partial`, or `insufficient`.
- `review_status`: `draft`, `reviewed`, `adjudicated`, or `disputed`.
- Boolean fields are strict booleans, not strings.
- Each discrepancy window requires `id`, `sku`, `start_ms`, and `end_ms` in video time.
- Balanced cases have no discrepancy windows. Discrepancy cases require at least one window.
- `requires_abstention` is an independently reviewed policy given *all permitted inputs*, not a label automatically inferred from video visibility.

The current API records review status as an operator assertion. It does not implement separate reviewer accounts, adjudication records, contributor identities, or publication licenses. Cases are immutable; use a new case ID to correct an annotation and freeze a new suite.

## Prediction import

A bundle requires `schema_version` (`1.0`), `suite_hash`, `input_track`, `model`, and `predictions`.

`model` requires string fields `id`, `version`, `provenance`, and an object `config`. Record your model weights/version and decision threshold there. `suite_hash` must exactly match the frozen suite; `input_track` must match the permitted inputs.

Each prediction requires `case_id`, `decision`, and `events`. Decisions are `no_action`, `discrepancy_alert`, or `abstain`. Alerts require at least one event with `id`, `sku`, and `t_ms`; other decisions require an empty event array. Duplicate/unknown cases are rejected. Missing predictions remain visible as exclusions.

The current import format is decision-only. It does not accept or calibrate confidence scores.

## Scoring policy

`tolerance_ms` expands reference windows; `cooldown_ms` deduplicates same-SKU alerts relative to the last retained prompt; `abstention_routes_to_review` determines abstention burden. These are versioned inputs, not hidden UI settings. Defaults of 1000 ms and 2000 ms come from the PRD and still require calibration.

Alerts match reference windows one-to-one by SKU and time using maximum bipartite matching. A transaction-level discrepancy is detected if at least one reference event matches; event recall separately exposes missed events. Raw prompt count remains visible after deduplication. Identity-specific matching and ambiguity flags are not yet implemented.

Every rate carries a numerator, denominator, value, and Wilson interval. Zero denominators produce JSON `null`, displayed as N/A. Wilson intervals assume independent trials; source-family bootstrap intervals are not implemented, and correlated observations must not be treated as independent evidence.

Pairs require exactly two same-family, same-split, same-truth cases. Pair metrics separate fully observable and reduced-visibility pairs and count incomplete pairs separately. This metadata validation does not establish that physical invariants were independently reviewed.

## API

Local route documentation is available at `/docs`, with the machine-readable specification at `/openapi.json`. Mutations require `X-CheckoutCheck: local`; browser requests must be same-origin. This is CSRF/DNS-rebinding mitigation for loopback development, **not authentication**.

| Route | Function |
| --- | --- |
| `GET /v1/state` | Workspace records and local runtime status |
| `GET /v1/health` | Database and worker readiness; returns 503 if degraded |
| `POST /v1/assets` | Raw `video/mp4` body; bounded validation before registration |
| `POST /v1/scan-logs/validate` | Parse supplied JSON/CSV and validate catalog, event order, voids, payment completeness and clock offset; no events are generated |
| `POST /v1/cases` | Register real evidence and separate reference annotation |
| `POST /v1/suites` | Freeze reviewed case IDs with a scoring policy |
| `POST /v1/runs` | Queue built-in analysis or imported predictions with an idempotency key |
| `GET /v1/runs/{id}` | Durable progress, report, evidence, and failures |
| `POST /v1/runs/{id}/cancel` | Idempotent cancellation |
| `GET /v1/media/{id}` | Local source media, including HTTP range support |
| `POST /v1/comparisons` | Compare two runs on the exact same frozen suite |
| `GET /v1/runs/{id}/export` | Private scoring bundle; media excluded |

The separate original-image benchmark also exposes:

| Route | Function |
| --- | --- |
| `GET /v1/perception` | Registered RPC subset, reference bank, methods and image run states |
| `POST /v1/perception/runs` | Queue an allowed method with an idempotency key |
| `GET /v1/perception/images/{image_id}` | Serve a registered original image after checksum verification |
| `POST /v1/perception/comparisons` | Compare scored image runs with matching dataset, evaluator and IoU threshold |

Image runs use the shared detail/cancel/export endpoints; their export is JSON rather than a transaction ZIP. Image results stay separate from transaction metrics. See [benchmark contracts and measured limitations](rpc-benchmark.md).

The original-video lab is a separate diagnostic workflow; it never registers a POS-grounded transaction case implicitly:

| Route | Function |
| --- | --- |
| `GET /v1/videos` | Registered original publisher videos and analysis availability |
| `GET /v1/videos/{id}/media` | Checksum-verified original MP4, with byte-range playback |
| `POST /v1/videos/{id}/analyze` | Bounded OpenCV subprocess; decode frames, retain publisher timestamp mapping, compute motion/sharpness diagnostics |
| `GET /v1/videos/{id}/analysis` | Per-frame diagnostics and separately labeled publisher interactions |
| `GET /v1/videos/{id}/export` | Diagnostic JSON with source and annotation hashes; no media bytes |

Video diagnostics use encoded frame index to map to the publisher's sampled source timestamps. Playback seconds and original source seconds are distinct fields. Publisher action intervals are mapped from normalized source duration, not from encoded playback duration. Missing action annotations remain missing.
