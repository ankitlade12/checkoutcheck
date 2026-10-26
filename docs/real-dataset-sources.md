# Real-data sources for CheckoutCheck

Reviewed October 26, 2026. This is a targeted source review, not an exhaustive inventory of every retail dataset. RPC original photographs and a six-video RetailAction subset are now installed and integrated locally. Full archives were not downloaded; synthetic files were excluded.

## Acquired original videos

The user requested internet videos. `python -m checkoutcheck.retail_video --groups 3` streams the publisher's validation archive and retains the first three complete groups: two original camera clips and the unmodified metadata per group. All six videos preserve publisher face blurring. These are 176 selected frames in total, not six continuous checkout transactions. No POS, payment, discrepancy, demographic or identity labels were invented.

The Real-video lab at `http://127.0.0.1:8765/#videos` plays the original MP4s, preserves publisher source-time mapping, displays publisher interaction points and runs OpenCV frame-difference/sharpness diagnostics. Two clips have no action annotations; the UI explicitly shows this missing annotation state. Publisher action labels are separate from computed diagnostics.

Source files, license, NOTICE, README, revision, archive member paths and SHA-256 checksums are stored under ignored `private-data/retailaction/`. The acquisition stops after the selected groups rather than storing the 1.94 GB archive. Files are used locally and have not been publicly uploaded. Run `python -m checkoutcheck.retail_video --analyze all` to regenerate diagnostics; exported diagnostics contain the original video hash and per-frame mapping, not video bytes.

## Candidate registry

| Source | Real material and intended use | Access | Published terms / limitations |
| --- | --- | --- | --- |
| [RPC](https://rpc-dataset.github.io/) | Controlled single-product and multi-product checkout photographs; recognition/counting | Official page links [Kaggle](https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset) and Baidu; advertised 15 GB | CC BY-NC-SA 4.0; academic use statement. Use original photographs, not the paper's synthetic/rendered baseline outputs. Images do not provide synchronized checkout transactions. |
| [RetailAction](https://huggingface.co/datasets/standard-cognition/RetailAction) | Operational-store videos with take/put/touch interaction labels; real human-object interaction evaluation | Publisher-hosted Hugging Face files; listing totals 31.9 GB | Custom license; see below. Clips use selected frames, so preserve metadata timestamps. POS/payment truth is not established by the documented annotations. |
| [AI City 2023 Track 4](https://www.aicitychallenge.org/2023-track4-download/) | Real staged checkout videos within a mixed release; closest video-task match | Publisher links Google Drive; current [access page](https://www.aicitychallenge.org/ai-city-challenge-dataset-access/) says this track remains available without the old request/password process | Training images are synthetic and must be excluded. Recorded Test A videos were originally supplied without labels; inspect current archive labels before evaluation. Restrictive license; see below. |
| [MVTec D2S](https://www.mvtec.com/research-teaching/datasets/mvtec-d2s) | Photographed groceries/products with instance masks; controlled segmentation benchmark | Publisher download form; public test annotations are withheld | CC BY-NC-SA 4.0. Use original captured images only. Not checkout video or POS data. |
| [SKU-110K](https://github.com/eg4000/SKU110K_CVPR19) | Real shelf images with dense product boxes; counting/detection robustness | Official repository links S3 archive and Google Drive | Author restricts use to academic/noncommercial purposes. Shelf localization does not establish SKU identity, a scan, or payment. |
| [MERL Shopping](https://www.merl.com/research/highlights/merl-shopping-dataset) | 106 overhead shopping videos, approximately two minutes each; temporal action recognition | [Official directory](https://www.merl.com/pub/tmarks/MERL_Shopping_Dataset/) lists 1.7 GB video archive, labels and README | Publisher describes research use. Check accompanying terms before redistribution. Shelf actions, not checkout payment records. |

## Material licensing/access findings

- RetailAction's [license](https://huggingface.co/datasets/standard-cognition/RetailAction/raw/main/LICENSE) requires author attribution, license/notice retention and deidentified use. It contains an additional-license requirement if revenue from products/services using the materials exceeds USD 10,000. This is not an unrestricted public-domain dataset.
- AI City's linked [2023 agreement](https://www.aicitychallenge.org/wp-content/uploads/2023/01/Dataset-License-AIC2023-12Jan2023.pdf) restricts commercial/production use, including trained models, and generally prohibits redistribution except specified limited research uses. Do not assume it permits a different hackathon's public demo or a future commercial MVP; resolve the intended use with the publisher before publication.
- RPC and D2S publish noncommercial/share-alike terms. Public download availability does not establish permission for every hosted demo, redistribution or future commercial use.
- Dataset download access and challenge evaluation-server access are separate. AI City's current access page removes the download request process for listed datasets, but still describes evaluation-account approval requirements.
- Follow publisher terms rather than a mirror's license badge. No institutional registration, publisher outreach or full-archive download was performed. The installed subsets retain the applicable publisher license and attribution.

## Real does not always mean live-store checkout

RetailAction documents operational stores. RPC, D2S and AI City's checkout videos include controlled or staged physical capture. Staged footage is camera-recorded real material, but must be labeled staged rather than presented as unobserved customer behavior. SKU-110K and MERL address adjacent shelf/perception tasks.

The [AI City task description](https://www.aicitychallenge.org/2023-data-and-evaluation/) explicitly separates synthetic training images from recorded checkout test videos. Never download the entire mixed release into a supposedly real-only benchmark without a file-level provenance filter.

## What remains missing

The reviewed sources do not establish an available complete benchmark of video + synchronized POS scan/void/payment events + independently reviewed physical transaction outcomes + matched legitimate-interaction pairs. This is a finding about these sources, not proof that no such dataset exists anywhere.

Consequently, do not fabricate scan logs for public footage and describe them as recorded transactions. Product boxes, action labels and shopping-list annotations are not evidence that a payment completed or that an intervention was unnecessary.

For full CheckoutCheck evaluation, obtain either:

1. Consented real staged recordings with actual mock POS logs captured during the performance, a synchronization cue, independently checked physical inventory, and documented permitted use; or
2. A partner-provided real dataset that explicitly includes those channels and sufficient rights.

## Recommended acquisition order

1. RPC original photographs for a product recognition/counting baseline, subject to intended-use rights. Preserve official train/validation/test boundaries and avoid rendering/augmentation workflows that violate the user's no-synthetic requirement.
2. Inspect AI City 2023's real-video subset metadata and access terms before selecting it for checkout motion testing. Its public original test split should not be relabeled as training while claiming an untouched official evaluation.
3. Use RetailAction only if interaction understanding is a concrete model requirement; selected frames and shelf actions make it unsuitable as a direct substitute for continuous checkout footage.
4. Add D2S, SKU-110K or MERL only for a specific segmentation, crowded-detection or temporal-action experiment. Dataset volume alone does not make the benchmark more valid.
5. Collect the small real transaction-grounded suite needed for CheckoutCheck's core matched-interaction evidence.

## Integration work before use

The transaction adapter expects ArUco-marked product videos. None of these public datasets is established as directly compatible with its POS contract. RPC now has separate original-image adapters, including a real-photo fine-tuned neural detector; RetailAction now has a separate source-video replay/diagnostics adapter. Keep both separate from transaction-level false-alert/recall metrics.

For every imported asset record publisher URL, source release, archive/file checksum, original split, real/staged provenance, label availability, license reference, permitted evaluation/publication scope, and timing transformations. Missing transaction truth remains unresolved; do not fill it from model predictions.

Exclude StandardSim, generated product renders, AI-generated videos and synthetic POS collections from this real-only acquisition plan. No synthetic files were created or downloaded.
