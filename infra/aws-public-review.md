# AWS judge hosting

Current endpoint: https://d2pt18a0j9tuil.cloudfront.net  
Product video: https://d2pt18a0j9tuil.cloudfront.net/demo

The judge window ends **November 3, 2026 at 00:00 UTC** (November 2 at 6 p.m. Central). A persistent systemd timer stops EC2 then. Retained EBS, the Elastic IP and other retained resources can still incur charges; the existing budget alert is not a hard spending cap. Extend the timer deliberately if judging requires a later date. Keep the host small for read-only review and resize before expensive new inference.

## Design

The private operator container binds host loopback port 8765. A separate container binds loopback port 8768, with `CHECKOUTCHECK_READ_ONLY=1`, no worker, a read-only root filesystem, a read-only data mount and dropped Linux capabilities. `CHECKOUTCHECK_REVIEW_DB=/data/outputs/public-review.sqlite` points to an online SQLite backup using DELETE journal mode. This avoids trying to map the live WAL journal through a read-only mount. Refresh that snapshot explicitly after new private runs complete.

Nginx port 80 proxies only the review service. The security group admits only AWS's CloudFront origin-facing prefix list. Nginx additionally checks a random `X-CheckoutCheck-Origin` header supplied by CloudFront. Keep its value private; the template parameter is `NoEcho`. Nginx rewrites Host to `127.0.0.1` for the application's trusted-host boundary. Requests are limited to 2 MB and rate limited. The public API independently blocks every mutation route and private transaction media/records. Only a comparison of existing perception reports permits POST and does not write data.

CloudFront supplies the HTTPS certificate and stable domain. The template allocates an Elastic IP for a stable origin hostname. Caching is disabled; evidence stays on EC2. The product video is served from `/data/outputs/checkoutcheck-product-demo.mp4`, with original-media credits and license copies on `/demo`.

## Recreate

1. Deploy the private stack and approved inputs using [aws-poc-operations.md](aws-poc-operations.md). Build the current source image. Do not expose the private operator port.
2. Through SSM, create the review snapshot with SQLite's `Connection.backup()`, set its journal mode to DELETE, and atomically replace `/opt/checkoutcheck/data/outputs/public-review.sqlite`. Close the backup before replacing it. Keep ownership readable by UID 10001.
3. Start the review container:

```sh
docker run -d --name checkoutcheck-review --restart unless-stopped \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -p 127.0.0.1:8768:8765 -v /opt/checkoutcheck/data:/data:ro \
  -e CHECKOUTCHECK_READ_ONLY=1 \
  -e CHECKOUTCHECK_REVIEW_DB=/data/outputs/public-review.sqlite \
  -e CHECKOUTCHECK_RUNTIME=aws_public_review checkoutcheck:poc
```

4. Configure nginx with a default-deny origin-header check, `proxy_pass http://127.0.0.1:8768`, `proxy_set_header Host 127.0.0.1`, a 2 MB body limit, and request-rate limiting. Do not put the origin secret in source control or logs.
5. Deploy [aws-public-review.json](aws-public-review.json), supplying the instance, security group, regional CloudFront prefix list and the same private origin secret. This template's hostname construction targets us-east-1.
6. Configure an explicit UTC end date in `checkoutcheck-stop.timer` using `OnCalendar`, `Persistent=true` and the existing shutdown service. Reload systemd and verify the timer. Maintain a small host and account budget alert; neither CloudFront nor a budget alert creates a hard spending limit.
7. Verify externally:

```sh
CHECKOUTCHECK_URL=https://YOUR_CLOUDFRONT_DOMAIN python3 tests/browser_public_review.py
```

Browser verification requires Playwright and an installed Chromium browser (`CHECKOUTCHECK_BROWSER` may specify its executable). It checks actual agent results, original clips, score comparisons, mobile layout and rejected writes. Unit checks cover private-record exclusion, query-only database access and no public worker startup.

## Evidence, updates and shutdown

COOL reports are in `/opt/checkoutcheck/data/outputs/cool/`; their checksums and method are in [cool-evaluation.md](../docs/cool-evaluation.md). The temporary Graviton instance has been terminated. Its Marketplace agreement remains active, but the software is billed by running instance usage; no COOL instance is retained.

Deploy source updates privately, rebuild both containers, refresh the snapshot, and repeat health/browser checks. Transfer generated evidence directly to EC2 when needed; do not upload results or backups to S3. Stopping EC2 makes both the application and video unavailable. After judging, delete the public-review stack to release its Elastic IP/distribution and ingress rule, then decide whether to retain the private stack's volume/bucket. Preserve required evidence before deleting storage.
