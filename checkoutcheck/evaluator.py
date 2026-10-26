"""Deterministic scoring; reference annotations never serve as model inputs."""

import hashlib
import json
from collections import Counter
from math import sqrt

VERSION = "checkoutcheck-evaluator/0.1.0"
DECISIONS = {"no_action", "discrepancy_alert", "abstain"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, required, optional=()):
    require(isinstance(value, dict), "Expected a JSON object")
    require(not (set(required) - value.keys()), f"Missing fields: {set(required) - value.keys()}")
    require(not (value.keys() - set(required) - set(optional)), "Unknown fields in object")


def identifier(value):
    require(isinstance(value, str) and 0 < len(value) <= 200, "Invalid identifier")


def milliseconds(value):
    require(type(value) is int and 0 <= value <= 3_600_000, "Invalid millisecond timestamp")


def events(values, windows=False):
    require(isinstance(values, list) and len(values) <= 1000, "Invalid event array")
    seen = set()
    for event in values:
        keys(event, ("id", "sku", "start_ms", "end_ms") if windows else ("id", "sku", "t_ms"))
        identifier(event["id"])
        identifier(event["sku"])
        require(event["id"] not in seen, "Duplicate event identifier")
        seen.add(event["id"])
        if windows:
            milliseconds(event["start_ms"])
            milliseconds(event["end_ms"])
            require(event["start_ms"] <= event["end_ms"], "Reversed reference window")
        else:
            milliseconds(event["t_ms"])


def validate_suite(suite):
    keys(suite, ("schema_version", "suite_id", "input_track", "evidence_kind", "policy", "cases"))
    require(suite["schema_version"] == "1.0", "Unsupported schema version")
    identifier(suite["suite_id"])
    identifier(suite["input_track"])
    identifier(suite["evidence_kind"])
    require(suite["input_track"] in {"V", "VP"}, "Unsupported input track")
    require(suite["evidence_kind"] in {"fixture", "synthetic", "staged"}, "Invalid evidence kind")
    keys(suite["policy"], ("tolerance_ms", "cooldown_ms", "abstention_routes_to_review"))
    for name in ("tolerance_ms", "cooldown_ms"):
        milliseconds(suite["policy"][name])
    require(type(suite["policy"]["abstention_routes_to_review"]) is bool, "Invalid review policy")
    require(isinstance(suite["cases"], list) and 0 < len(suite["cases"]) <= 1000, "Suite must contain 1–1000 cases")
    seen, groups, pairs = set(), {}, {}
    for case in suite["cases"]:
        keys(case, ("id", "family_id", "session_id", "split", "truth", "visibility", "review_status",
                    "rights_valid", "input_valid", "requires_abstention", "discrepancies"), ("pair_id",))
        for field in ("id", "family_id", "session_id"):
            identifier(case[field])
        for field in ("split", "truth", "visibility", "review_status"):
            identifier(case[field])
        require(case["id"] not in seen, "Duplicate case identifier")
        seen.add(case["id"])
        require(case["split"] in {"development", "calibration", "holdout"}, "Invalid split")
        require(case["truth"] in {"balanced", "discrepancy", "unresolved"}, "Invalid transaction truth")
        require(case["visibility"] in {"sufficient", "partial", "insufficient"}, "Invalid visibility")
        require(case["review_status"] in {"draft", "reviewed", "adjudicated", "disputed"}, "Invalid review status")
        for field in ("rights_valid", "input_valid", "requires_abstention"):
            require(type(case[field]) is bool, f"{field} must be boolean")
        events(case["discrepancies"], windows=True)
        require(case["truth"] != "balanced" or not case["discrepancies"], "Balanced case has discrepancies")
        require(case["truth"] != "discrepancy" or bool(case["discrepancies"]), "Discrepancy case needs reference windows")
        for field in ("family_id", "session_id"):
            group = (field, case[field])
            require(group not in groups or groups[group] == case["split"], "Family/session leakage across splits")
            groups[group] = case["split"]
        if "pair_id" in case:
            identifier(case["pair_id"])
            pairs.setdefault(case["pair_id"], []).append(case)
    for pair in pairs.values():
        require(len(pair) == 2, "A declared pair must contain exactly two cases")
        require(len({(c['family_id'], c['split'], c['truth']) for c in pair}) == 1,
                "Pairs must share a family, split, and transaction truth")


def validate_predictions(bundle, suite):
    keys(bundle, ("schema_version", "suite_hash", "input_track", "model", "predictions"))
    require(bundle["schema_version"] == "1.0", "Unsupported prediction schema")
    require(bundle["suite_hash"] == digest(suite), "Predictions reference a different suite hash")
    require(bundle["input_track"] == suite["input_track"], "Input track mismatch")
    keys(bundle["model"], ("id", "version", "config", "provenance"))
    for field in ("id", "version", "provenance"):
        identifier(bundle["model"][field])
    require(isinstance(bundle["model"]["config"], dict), "Model config must be an object")
    known = {c["id"] for c in suite["cases"]}
    require(isinstance(bundle["predictions"], list) and len(bundle["predictions"]) <= len(known), "Invalid prediction array")
    seen = set()
    for prediction in bundle["predictions"]:
        keys(prediction, ("case_id", "decision", "events"))
        identifier(prediction["case_id"])
        require(prediction["case_id"] in known, "Prediction references an unknown case")
        require(prediction["case_id"] not in seen, "Duplicate prediction for case")
        seen.add(prediction["case_id"])
        identifier(prediction["decision"])
        require(prediction["decision"] in DECISIONS, "Invalid model decision")
        events(prediction["events"])
        require((prediction["decision"] == "discrepancy_alert") == bool(prediction["events"]),
                "Alerts require evidence events; other decisions cannot contain alerts")


def rate(numerator, denominator):
    """Wilson interval is descriptive; correlated cases are not independent trials."""
    if not denominator:
        return {"numerator": numerator, "denominator": 0, "value": None, "wilson_95": None}
    p, z = numerator / denominator, 1.959963984540054
    scale = 1 + z * z / denominator
    center = (p + z * z / (2 * denominator)) / scale
    half = z * sqrt(p * (1 - p) / denominator + z * z / (4 * denominator ** 2)) / scale
    return {"numerator": numerator, "denominator": denominator, "value": p,
            "wilson_95": [max(0, center - half), min(1, center + half)]}


def match_events(predicted, reference, tolerance, cooldown):
    # Maximum bipartite matching avoids greedy undercounting of overlapping windows.
    deduped, last = [], {}
    for event in sorted(predicted, key=lambda e: (e["t_ms"], e["id"])):
        sku, time = event["sku"], event["t_ms"]
        if sku not in last or time - last[sku] > cooldown:
            deduped.append(event)
            last[sku] = time
    edges = [[j for j, ref in enumerate(reference)
              if event["sku"] == ref["sku"] and ref["start_ms"] - tolerance <= event["t_ms"] <= ref["end_ms"] + tolerance]
             for event in deduped]
    matched = {}

    def assign(index, visited):
        for target in edges[index]:
            if target in visited:
                continue
            visited.add(target)
            if target not in matched or assign(matched[target], visited):
                matched[target] = index
                return True
        return False

    for index in range(len(deduped)):
        assign(index, set())
    return [{"prediction_id": deduped[i]["id"], "reference_id": reference[j]["id"]}
            for j, i in sorted(matched.items())]


def score(suite, predictions):
    validate_suite(suite)
    validate_predictions(predictions, suite)
    policy = suite["policy"]
    by_id = {p["case_id"]: p for p in predictions["predictions"]}
    rows = []
    for case in suite["cases"]:
        reasons = []
        if not case["rights_valid"]:
            reasons.append("insufficient_rights")
        if not case["input_valid"]:
            reasons.append("invalid_input")
        if case["truth"] == "unresolved":
            reasons.append("unresolved_truth")
        if case["review_status"] not in {"reviewed", "adjudicated"}:
            reasons.append("unreviewed_or_disputed")
        if case["id"] not in by_id:
            reasons.append("missing_prediction")
        row = {"case_id": case["id"], "split": case["split"], "visibility": case["visibility"],
               "truth": case["truth"], "exclusions": reasons, "findings": []}
        if reasons:
            rows.append(row)
            continue
        prediction = by_id[case["id"]]
        matches = match_events(prediction["events"], case["discrepancies"],
                               policy["tolerance_ms"], policy["cooldown_ms"])
        decision = prediction["decision"]
        if case["truth"] == "balanced" and decision == "discrepancy_alert":
            row["findings"].append("false_alert")
        if case["truth"] == "discrepancy" and not matches:
            row["findings"].append("missed_discrepancy")
        if case["requires_abstention"] and decision != "abstain":
            row["findings"].append("unsupported_certainty")
        row.update(decision=decision, matches=matches, raw_prompt_count=len(prediction["events"]),
                   reference_event_count=len(case["discrepancies"]), requires_abstention=case["requires_abstention"])
        rows.append(row)

    def metrics(selected):
        scored = [r for r in selected if not r["exclusions"]]
        balanced = [r for r in scored if r["truth"] == "balanced"]
        discrepancy = [r for r in scored if r["truth"] == "discrepancy"]
        challenges = [r for r in scored if r["requires_abstention"]]
        detected = sum(bool(r["matches"]) for r in discrepancy)
        return {
            "processing_coverage": rate(len(scored), len(selected)),
            "false_alert_rate": rate(sum("false_alert" in r["findings"] for r in balanced), len(balanced)),
            "discrepancy_recall": rate(detected, len(discrepancy)),
            "missed_discrepancy_rate": rate(len(discrepancy) - detected, len(discrepancy)),
            "abstentions_on_discrepancies": sum(r["decision"] == "abstain" for r in discrepancy),
            "intervention_burden": rate(sum(r["decision"] == "discrepancy_alert" or
                (r["decision"] == "abstain" and policy["abstention_routes_to_review"]) for r in balanced), len(balanced)),
            "abstention_rate": rate(sum(r["decision"] == "abstain" for r in scored), len(scored)),
            "unsupported_certainty": rate(sum("unsupported_certainty" in r["findings"] for r in challenges), len(challenges)),
            "event_recall": rate(sum(len(r["matches"]) for r in discrepancy), sum(r["reference_event_count"] for r in discrepancy)),
            "raw_prompt_count": sum(r["raw_prompt_count"] for r in scored),
        }

    by_case = {r["case_id"]: r for r in rows}
    pairs = {}
    for case in suite["cases"]:
        if "pair_id" in case:
            pairs.setdefault(case["pair_id"], []).append(case)
    pair_groups = {}
    for pair in pairs.values():
        group = "fully_observable" if all(c["visibility"] == "sufficient" for c in pair) else "reduced_visibility"
        summary = pair_groups.setdefault(group, {"complete": 0, "incomplete": 0, "changed": 0})
        members = [by_case[c["id"]] for c in pair]
        if any(c["exclusions"] for c in members):
            summary["incomplete"] += 1
        else:
            summary["complete"] += 1
            summary["changed"] += members[0]["decision"] != members[1]["decision"]
    return {"evaluator_version": VERSION, "suite_hash": digest(suite), "prediction_hash": digest(predictions),
            "evidence_kind": suite["evidence_kind"], "prediction_origin": "prediction_bundle",
            "input_track": suite["input_track"], "policy": policy, "model": predictions["model"],
            "status": "completed" if all(not r["exclusions"] for r in rows) else "partial",
            "metrics": metrics(rows),
            "by_split": {s: metrics([r for r in rows if r["split"] == s]) for s in sorted({r["split"] for r in rows})},
            "by_visibility": {v: metrics([r for r in rows if r["visibility"] == v]) for v in sorted({r["visibility"] for r in rows})},
            "exclusion_counts": dict(Counter(reason for r in rows for reason in r["exclusions"])),
            "paired_outcome_change": {group: {"rate": rate(v["changed"], v["complete"]), "incomplete_pairs": v["incomplete"]}
                                      for group, v in pair_groups.items()},
            "cases": rows,
            "limitations": ["Scoring alone does not verify inference; consult the execution provenance.",
                            "Wilson intervals assume independent trials; family-correlated cases need group-aware analysis.",
                            "Fixture results do not measure real-world model performance." if suite["evidence_kind"] == "fixture"
                            else "Scenario results do not establish population fairness or accessibility."]}


def compare(suite, baseline, candidate):
    before, after = score(suite, baseline), score(suite, candidate)
    changes = []
    for old, new in zip(before["cases"], after["cases"]):
        if old["exclusions"] or new["exclusions"]:
            state = "incomplete"
        elif old["findings"] == new["findings"] and old["decision"] == new["decision"]:
            state = "unchanged"
        else:
            # A decision change is not automatically an improvement.
            state = "changed"
        changes.append({"case_id": old["case_id"], "state": state, "before": old, "after": new})
    return {"suite_hash": digest(suite), "baseline": before, "candidate": after, "changes": changes}
