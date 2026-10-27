# Verified private AWS deployment — October 26, 2026

CheckoutCheck was deployed and exercised in a private AWS deployment in us-east-1. The private EC2 worker uses a scoped instance role, encrypted EBS, private encrypted S3 inputs, CloudWatch application logs and an IAM-authorized Session Manager tunnel. No inbound security-group rules or application login were added.

## Actual execution

All five image methods completed on 24 original RPC photographs with 291 labeled objects. Each exported score was independently recomputed locally and matched its report. Six original RetailAction clips (176 frames) passed playback, seeking, source timestamp mapping, diagnostics, range requests and export through the AWS tunnel. Browser checks passed with zero JavaScript or HTTP errors, including cancellation, reload persistence, overlays, comparison and mobile layout.

| Method | Matched objects | Precision | Recall | Cloud run elapsed |
| --- | --- | --- | --- | --- |
| fasterrcnn-rpc-v1 | 105/291 | 74.47% | 36.08% | 49.5 s |
| fasterrcnn-coco-v1 | 13/291 | 92.86% | 4.47% | 154.6 s |
| sift-reference-v1 | 48/291 | 61.54% | 16.49% | 52.3 s |
| watershed-v1 | 37/291 | 18.23% | 12.71% | 5.3 s |
| foreground-components-v1 | 17/291 | 14.17% | 5.84% | 3.5 s |

Times are observations from this burst-limited CPU, not latency guarantees. The initial COCO attempt exceeded the original 180-second cap; it remains recorded as failed. The worker limit was raised to a bounded 600 seconds and the affected neural checks passed. Cloud SIFT and watershed results differ slightly from macOS results; cloud exports are retained separately rather than claiming bitwise platform invariance.

## Reproduction and access

`private-data/aws-verification.json` records run IDs, hashes, runtime versions, image ID and checks. `private-data/aws-deployment.json` contains the actual stack outputs. The installed runtime is CPU-only PyTorch 2.14.1 and OpenCV 5.0.0 on Amazon Linux 2023's x86-64 host. No AWS credentials were put into the container or source archive.

Use `./start-aws.command` to start the worker and open the private tunnel, then visit http://127.0.0.1:8766. Starting compute incurs charges. The worker has a two-hour stop timer on every boot and a $10 monthly budget alert (not a hard cap). Storage and retained logs still incur charges while EC2 is stopped. The local app remains at http://127.0.0.1:8765.

## Backup and remaining limits

SQLite's online backup API captured five completed runs, one canceled run and the initial failed run. Restoration into an isolated database passed its integrity check. There are zero transaction cases. Per the user's instruction, the backup remains on EC2 at `/opt/checkoutcheck/data/outputs/cloud-workbench.sqlite`; generated results and backups were not uploaded to S3. Deleting the instance/root volume would delete this backup.

The recorded AWS walkthrough is a private local artifact under `artifacts/aws-demo-recording/`; it has no fabricated observations or narration. Human team introduction, final publication/judge access and submission are still outstanding. Real synchronized checkout video/POS evidence remains unavailable, so transaction accuracy and the full community MVP are not certified. The best image detector still misses 186 of 291 objects.


## Public review, Agentic Vision and COOL update

The current [HTTPS judge endpoint](https://d2pt18a0j9tuil.cloudfront.net) serves a separate read-only container and the [4:11 narrated product demo](https://d2pt18a0j9tuil.cloudfront.net/demo). The host is now t3.small for review; the original five baseline measurements above were made on t3.large. A persistent shutdown timer ends the review window on November 3, 2026 at 00:00 UTC. CloudFront and a stable Elastic IP preserve the endpoint across the resize. The origin accepts only CloudFront traffic and verifies a private header; public mutations/private transaction media are blocked.

The actual agent run on t3.large completed all 24 images: 18 neural routes, six watershed routes, 17 inspection recommendations, 72 tool calls and zero budget violations. It scored 94 true positives, 53 false positives and 197 misses. This is lower recall than the trained detector alone. See [agent evaluation](agentic-vision.md).

An official COOL Marketplace instance on c8g.large executed both application pipelines against stock OpenCV on the same original photos. Observed median speedups were 1.033× and 1.041×, with identical evaluation scores. Version/order limitations and reproducible inputs are documented in [COOL evaluation](cool-evaluation.md). Full reports were transferred directly to the persistent EC2 volume, checksum-verified, and the temporary Graviton instance was terminated. No generated reports or database backups were uploaded to S3.
