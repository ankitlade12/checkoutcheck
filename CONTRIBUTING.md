# Contributing to CheckoutCheck

Contributions that improve reproducibility, real-data inspection, detector evaluation and accessibility are welcome.

1. Open an issue describing the problem, supported conditions and a minimal reproduction. Do not attach credentials, customer details or private recordings.
2. Set up the pinned environment using the README. Use a branch for the change.
3. Keep predictions and reference annotations separate. Preserve source attribution, hashes, split boundaries and explicit exclusions.
4. Run `python -m unittest discover -s tests -v` and Node syntax checks. If changing image/video behavior, run the relevant browser flow with authorized originals and report what was actually tested.
5. Submit a pull request explaining the resulting behavior, verification and remaining limits.

## Data contributions

Never add datasets, model weights, generated footage, invented scan logs or private annotation exports to Git. Discuss a source and its rights first, then use the [capture protocol](docs/real-dataset-sources.md#real-transaction-capture-protocol) or [source registry](docs/real-dataset-sources.md). Evaluation permission does not automatically permit public distribution.

Temporary numeric/parser inputs are appropriate for software tests. They must not be installed as product evidence or presented as recorded transactions. An image box or shelf-action annotation does not establish scan or payment truth.

## Project scope

The hackathon application is private and single-operator. Accounts and collaboration belong to the separately scoped community roadmap. Keep changes focused, document unsupported conditions, and avoid claims of checkout accuracy without real synchronized evidence.
