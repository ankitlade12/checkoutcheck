# Architecture

## High-level workflow

```mermaid
flowchart LR
    subgraph S1["STEP 1: ORIGINAL INPUTS"]
      I["Original RPC validation photographs"] --> V["Verify source manifest and checksums"]
    end
    subgraph S2["STEP 2: PERCEPTION"]
      V --> O["OpenCV 5: decode, sharpness, foreground"]
      O --> P{"Observed quality and density"}
      P -->|Dense or warning| N["RPC neural detector"]
      P -->|Clear foreground| W["OpenCV watershed"]
    end
    subgraph S3["STEP 3: DECISION + TRACE"]
      N --> T["Record observations, selected tool and timings"]
      W --> T
      P -->|Low sharpness| H["Recommend human inspection"]
      T -->|Failure or count disagreement| H
    end
    subgraph S4["STEP 4: EVALUATE + REVIEW"]
      T --> E["Score predictions against reference annotations"]
      R["Reference labels: scoring only"] --> E
      E --> X["Inspect overlays, compare and export"]
      H --> X
    end
    style I fill:#e1f5ff,stroke:#0288d1
    style O fill:#fff4e1,stroke:#f57c00
    style P fill:#fff4e1,stroke:#f57c00
    style T fill:#f3e5f5,stroke:#7b1fa2
    style H fill:#fce4ec,stroke:#c2185b
    style E fill:#c8e6c9,stroke:#388e3c
    style X fill:#c8e6c9,stroke:#388e3c
```

## System architecture

```mermaid
flowchart TB
    J["JUDGE / COMMUNITY BROWSER"]
    U["PRIVATE OPERATOR"]
    subgraph ACCESS["ACCESS + APPLICATION LAYER"]
      CF["CloudFront HTTPS + restricted nginx origin"]
      RO["Read-only FastAPI service / no worker"]
      SSM["IAM-authorized Session Manager"]
      API["Private FastAPI / uploads and job requests"]
    end
    subgraph CORE["CORE VISION + EVALUATION SERVICES — EC2"]
      Q["SQLite queue + bounded worker"]
      CV["OpenCV 5 preprocessing and diagnostics"]
      A["Deterministic vision agent / max 3 calls"]
      D["Watershed or PyTorch detector"]
      E["Evaluator / reference labels enter here"]
      H["Human inspection recommendation + trace"]
    end
    subgraph DATA["STORAGE + OBSERVABILITY"]
      S3["Private encrypted S3 / original inputs + weights"]
      DB["EC2 volume / SQLite results + backups"]
      SNAP["Read-only SQLite review snapshot"]
      CW["CloudWatch application logs"]
    end
    subgraph BENCH["SEPARATE COOL BENCHMARK"]
      G["Official COOL / c8g.large Graviton"]
      B["Same real inputs + pipelines / stock baseline"]
      F["Reports retained on project EC2 / benchmark instance terminated"]
    end
    J --> CF --> RO --> SNAP
    U --> SSM --> API --> Q --> CV --> A --> D --> E --> DB
    A --> H
    S3 --> Q
    Q --> CW
    DB --> SNAP
    G --> B --> F --> DB
    style J fill:#e1f5ff,stroke:#0288d1,stroke-width:2px
    style U fill:#e1f5ff,stroke:#0288d1
    style CV fill:#fff4e1,stroke:#f57c00,stroke-width:2px
    style A fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    style E fill:#c8e6c9,stroke:#388e3c
    style H fill:#fce4ec,stroke:#c2185b
    style G fill:#ffe0b2,stroke:#e64a19,stroke-width:2px
```

The evaluator has no image-processing dependency. Model inference receives only media and permitted transaction/catalog/configuration fields. The trusted subprocess does not receive the suite's reference annotations. This is an explicit data-flow boundary, not an OS security boundary against hostile model code; arbitrary executable adapters are unsupported.

Suite hashes include a digest of registered case entries, which bind video checksums, input events, preprocessing configuration, and labels. Runs use idempotency keys, immutable suite references, one sequential worker, and atomic final-result commits. A partial result keeps failed/missing cases visible and excludes them from metric denominators while reducing processing coverage.

The local UI uses buildless HTML, CSS, and JavaScript. This was chosen to keep the review client inspectable and avoid a separate frontend toolchain; it is a documented departure from the PRD's proposed React stack. Python/FastAPI handles API and orchestration; SQLite holds persistent local metadata. Large media stays outside the database and source tree.

## Login-free hackathon deployment

The private operator application uses EC2, a scoped instance role, private encrypted S3 inputs, CloudWatch logs and IAM-authorized Session Manager forwarding. A separate public review container serves completed results through CloudFront HTTPS. Only CloudFront can reach the origin port, and nginx also validates a private origin header. The public API allows only reviewed read paths plus a side-effect-free comparison operation. It has no worker and reads a consistent SQLite snapshot from a read-only volume. Private transaction media and mutation routes are blocked.

The worker keeps its original writable database. Backups, agent traces and COOL reports remain on EC2; generated results are not uploaded to S3. The temporary COOL instance ran the actual application pipelines on the official Arm runtime, transferred its reports directly over a restricted VPC connection, and was terminated after checksum verification.

![AWS, OpenCV and agent architecture](architecture.svg)

![Evidence-to-review workflow](workflow.svg)

See [private deployment](../infra/aws-poc.json), [public review deployment](../infra/aws-public-review.json), [agent workflow](agentic-vision.md), [COOL evaluation](cool-evaluation.md) and [technical report](technical-report.md). A static frontend alone would not demonstrate the AWS workload; actual cloud inference and benchmark evidence are available in the application.
