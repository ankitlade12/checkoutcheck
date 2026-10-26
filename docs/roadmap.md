# Roadmap and acceptance criteria

The current release is a verified private image/video POC. The transaction evaluator is implemented, but its real checkout evidence gate remains open. The future community MVP is planned, not a shipped multi-user service.

## Scope

- Use original captured data and recorded events. Never manufacture missing POS or physical-reference truth.
- Keep the hackathon application private and login-free, using localhost or an authorized SSM tunnel.
- Keep model predictions separate from reference annotations and disclose unsupported conditions.
- Add infrastructure only when the verified user workflow requires it. The existing EC2/SQLite deployment is sufficient for the current single-operator scope.

## POC completion gates

Image perception, original-video diagnostics, private AWS execution, scoring exports and recovery checks are recorded in [implementation status](implementation-status.md). Remaining transaction gates require permissioned recordings, actual scan/void/payment event logs, independent inventory review, measured synchronization and repeatable marker tracking under declared capture conditions. See [capture protocol](capture-protocol.md).

The submission gate additionally requires team details, a reviewed final demo, judge access and organizer-rule review. A negative model result can be valid engineering evidence; favorable accuracy is not a substitute for a correct experiment.

## Functional requirement ledger

| Requirement | Current foundation | Remaining acceptance evidence |
| --- | --- | --- |
| FR01 Access | Private single-operator boundary | For the later pilot: membership, revocation and cross-project isolation tests; accounts are excluded from this hackathon |
| FR02 Ingestion | Bounded MP4 and JSON/CSV validation | Real upload/codec coverage, interruption handling, quarantine lifecycle and aggregate quotas |
| FR03 Versions | Immutable case/suite hashes and split checks | Catalog/annotation revisions, corrections and traceable affected results |
| FR04 Alignment | Explicit offset and source timestamp mapping | Measured tolerance, drift and variable-frame-rate behavior on real paired recordings |
| FR05 Execution | Marker adapter, five image methods and imported predictions | Supported unmarked-product tracking, calibrated uncertainty and independent held-out validation |
| FR06 Scoring | Matching, exclusions, rates and raw burden | Ambiguous-instance policies, calibrated tolerances and family-aware uncertainty |
| FR07 Replay | Original video, separate overlays, all alerts and reference boundaries | Reviewer task success and measured transaction temporal accuracy |
| FR08 Pairs | Pair/split/visibility validation | Independent invariant-review evidence and complete/incomplete pair reporting |
| FR09 Isolation | Full source context and event seeking | Context-preserving failure reduction with a rerun predicate; invalid reductions must be rejected |
| FR10 Export | Recomputable scoring and manifests | Rights-filtered media export and independent clean-environment inference replay |
| FR11 Lifecycle | Persistent single-worker queue, retry and cancel | Distributed leases, heartbeat, expiry, quotas and duplicate-delivery recovery when scaling |
| FR12 Review | Operator review declaration | Independent reviewers, disputes, adjudication, correction audit and affected-run notices |
| FR13 Controller | Bounded rule-based abstention/review trace | Evaluated perception-driven next actions with fixed budgets; no authority to change truth |
| FR14 CI | CLI verification and source checks | Versioned regression policies distinguishing regressions, infrastructure failures and insufficient evidence |

## Community MVP sequence

1. Acquire the real synchronized checkout suite and validate the supported detector conditions.
2. Implement independent annotation review, revisions, evaluation/publication permissions and withdrawal/deletion across derivatives.
3. Introduce project isolation and identities only for the separately scoped multi-user pilot.
4. Move from SQLite/single worker only when concurrent usage requires it; evaluate PostgreSQL and durable queued workers with tested migrations and recovery.
5. Test external-user onboarding, reproducibility, accessibility, load, security and operational recovery.
6. Record acceptance evidence and maintainer ownership before labeling a community release ready.

Potential future AWS services include RDS PostgreSQL, SQS, ECS, managed identity and HTTPS. They are options for future requirements, not additional services needed to run today's POC. GPUs and LLM services are not prerequisites.

## Whole-product requirements retained

Beyond FR01–FR14, completion requires practitioner feedback, a supported prior-art/claims record, documented data/model rights, a maintained threat model, quotas, consent withdrawal, derivative/backup deletion behavior, measured performance and accessibility, cost/maintenance ownership, contribution/support routes, reproducible release records and independent pilot acceptance. These requirements survive consolidation of the earlier planning documents.

For each future gate record its status, code/artifact, environment, date, reviewer, measured outcome and limits. No cloud service or generated dataset can supply missing real transaction truth.
