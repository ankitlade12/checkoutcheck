# Real-data capture protocol

No dataset is supplied or generated. Use this protocol when collecting real staged recordings; do not present a capture target as completed data collection.

1. Obtain permission for private evaluation. Obtain separate, explicit permission before publishing any recording or including it in a competition video. Avoid faces, identifying audio, genuine receipts, and payment details.
2. Use a stable camera and initially empty checkout area. Keep the bagging region on the right. For the built-in adapter, attach a unique `DICT_4X4_50` marker to every product instance and record its SKU mapping. Unmarked merchandise is unsupported.
3. Record the transaction script, starting inventory, intended movements, and final physical inventory independently of the model. A scan log alone does not establish truth.
4. Record a visible synchronization cue linked to the mock POS clock. Establish the constant clock offset. If clocks drift, correct the capture setup or document normalization and revalidate alignment; do not silently shift events.
5. Capture normal checkout and legitimate variants such as assisted handoff, pauses, and rearrangement. Capture staged omitted/duplicate scans as separately labeled discrepancies without implying intent. Keep source sessions and paired variants together in one split.
6. Keep every product marker visible through payment when testing the supported baseline. Record occlusion as a visibility condition rather than treating every uncertain result as a false alert.
7. Have a second reviewer check physical inventory, scan additions/voids, payment completeness, discrepancy windows, observability, and the expected response. If only one reviewer is available, disclose that limitation.
8. Add the recording and actual mock event records through the interface. Freeze only reviewed cases. Preserve the original media and its SHA-256 checksum.
9. Report achieved case counts, source families, exclusions, failures, and uncertainty. Never extrapolate a handful of acted recordings into a claim about population fairness or commercial checkout reliability.

The current application stores only an evaluation-rights declaration, not a consent management system. Keep contributor permission documents securely outside the repository. Retention and complete derivative deletion must be implemented before accepting sensitive footage from community contributors at scale.
