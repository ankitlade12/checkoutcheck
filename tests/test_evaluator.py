"""Hand-calculated software checks only; these are not a product dataset."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from checkoutcheck.evaluator import compare, digest, match_events, score, validate_suite
from checkoutcheck.vision import validate_inputs


def case(identifier="case", **changes):
    value = {"id": identifier, "family_id": identifier, "session_id": identifier, "split": "development",
        "truth": "balanced", "visibility": "sufficient", "review_status": "reviewed", "rights_valid": True,
        "input_valid": True, "requires_abstention": False, "discrepancies": []}
    value.update(changes)
    return value


def suite(cases=None):
    return {"schema_version": "1.0", "suite_id": "unit-test", "input_track": "VP", "evidence_kind": "staged",
        "policy": {"tolerance_ms": 1000, "cooldown_ms": 2000, "abstention_routes_to_review": True},
        "cases": cases if cases is not None else [case()]}


def bundle(source, decisions=None):
    return {"schema_version": "1.0", "suite_hash": digest(source), "input_track": "VP",
        "model": {"id": "unit-test", "version": "1", "config": {}, "provenance": "Hand-calculated software test"},
        "predictions": decisions if decisions is not None else [{"case_id": c["id"], "decision": "no_action", "events": []} for c in source["cases"]]}


def inputs():
    return {"catalog": {"0": "sku"}, "offset_ms": 0, "bagging_x": .6, "min_observations": 3,
        "events": [{"id": "scan", "type": "scan_add", "t_ms": 1000, "sku": "sku", "quantity": 1},
                   {"id": "pay", "type": "payment_complete", "t_ms": 3000}]}


class EvaluationTests(unittest.TestCase):
    def test_zero_denominator_is_unavailable(self):
        source = suite()
        result = score(source, bundle(source))
        self.assertIsNone(result["metrics"]["discrepancy_recall"]["value"])
        self.assertEqual(result["metrics"]["false_alert_rate"]["value"], 0)

    def test_false_alert_and_abstention_are_separate(self):
        source = suite([case("a"), case("b")])
        predictions = bundle(source, [{"case_id": "a", "decision": "discrepancy_alert", "events": [{"id": "alert", "sku": "s", "t_ms": 5}]},
            {"case_id": "b", "decision": "abstain", "events": []}])
        metrics = score(source, predictions)["metrics"]
        self.assertEqual(metrics["false_alert_rate"]["value"], .5)
        self.assertEqual(metrics["intervention_burden"]["value"], 1)
        self.assertEqual(metrics["abstention_rate"]["value"], .5)

    def test_alert_must_match_reference_to_detect_discrepancy(self):
        source = suite([case(truth="discrepancy", discrepancies=[{"id":"ref", "sku":"x", "start_ms":4000,"end_ms":4500}])])
        prediction = bundle(source,[{"case_id":"case", "decision":"discrepancy_alert", "events":[{"id":"p","sku":"wrong","t_ms":4200}]}])
        result = score(source,prediction)
        self.assertIn("missed_discrepancy",result["cases"][0]["findings"])

    def test_matching_is_one_to_one_and_keeps_raw_prompts(self):
        source = suite([case(truth="discrepancy", discrepancies=[{"id":"ref", "sku":"x", "start_ms":4000,"end_ms":4500}])])
        prediction = bundle(source,[{"case_id":"case", "decision":"discrepancy_alert", "events":[{"id":str(i),"sku":"x","t_ms":4200+i} for i in range(3)]}])
        metrics = score(source,prediction)["metrics"]
        self.assertEqual(metrics["event_recall"]["numerator"],1)
        self.assertEqual(metrics["raw_prompt_count"],3)

    def test_maximum_matching_not_greedy(self):
        references=[{"id":"wide","sku":"s","start_ms":0,"end_ms":10},{"id":"narrow","sku":"s","start_ms":0,"end_ms":2}]
        events=[{"id":"first","sku":"s","t_ms":1},{"id":"second","sku":"s","t_ms":9}]
        self.assertEqual(len(match_events(events,references,0,0)),2)

    def test_excluded_cases_do_not_become_model_errors(self):
        source=suite([case("a",input_valid=False),case("b",truth="unresolved"),case("c",review_status="disputed"),case("d",rights_valid=False)])
        result=score(source,bundle(source))
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["metrics"]["processing_coverage"]["numerator"],0)
        self.assertIsNone(result["metrics"]["false_alert_rate"]["value"])

    def test_missing_predictions_count_against_coverage(self):
        source=suite()
        result=score(source,bundle(source,[]))
        self.assertEqual(result["exclusion_counts"],{"missing_prediction":1})

    def test_unsupported_certainty_is_independent(self):
        source=suite([case(visibility="insufficient",requires_abstention=True)])
        result=score(source,bundle(source))
        self.assertEqual(result["metrics"]["unsupported_certainty"]["value"],1)
        self.assertEqual(result["metrics"]["false_alert_rate"]["value"],0)

    def test_hash_and_track_mismatch_rejected(self):
        source=suite()
        for field,value in (("suite_hash","wrong"),("input_track","V")):
            prediction=bundle(source);prediction[field]=value
            with self.assertRaises(ValueError):score(source,prediction)

    def test_leakage_rejected_for_families_and_sessions(self):
        for field in ("family_id","session_id"):
            source=suite([case("a"),case("b",split="holdout",**{field:"a"})])
            with self.assertRaisesRegex(ValueError,"leakage"):validate_suite(source)

    def test_malformed_labels_and_predictions_rejected(self):
        for change in ({"truth":[]},{"rights_valid":"yes"},{"id":""}):
            with self.assertRaises(ValueError):validate_suite(suite([case(**change)]))
        source=suite();predictions=bundle(source)
        predictions["predictions"][0]["decision"]="discrepancy_alert"
        with self.assertRaises(ValueError):score(source,predictions)

    def test_pairs_require_matching_truth_and_both_members(self):
        source=suite([case("a",family_id="pair",pair_id="p"),case("b",family_id="pair",pair_id="p")])
        result=score(source,bundle(source,[]))
        self.assertEqual(result["paired_outcome_change"]["fully_observable"]["incomplete_pairs"],1)
        source["cases"].pop()
        with self.assertRaises(ValueError):validate_suite(source)

    def test_comparison_marks_incomplete_instead_of_improvement(self):
        source=suite()
        result=compare(source,bundle(source),bundle(source,[]))
        self.assertEqual(result["changes"][0]["state"],"incomplete")

    def test_export_reproduces_and_detects_tampering(self):
        source=suite()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'suite.json').write_text(json.dumps(source))
            (root/'pred.json').write_text(json.dumps(bundle(source)))
            command=[sys.executable,'-m','checkoutcheck']
            exported=subprocess.run(command+['export',str(root/'suite.json'),str(root/'pred.json'),str(root/'export')],capture_output=True)
            self.assertEqual(exported.returncode,0,exported.stderr)
            verified=subprocess.run(command+['verify',str(root/'export')],capture_output=True)
            self.assertEqual(verified.returncode,0,verified.stderr)
            report=json.loads((root/'export/report.json').read_text());report['status']='tampered'
            (root/'export/report.json').write_text(json.dumps(report))
            self.assertEqual(subprocess.run(command+['verify',str(root/'export')],capture_output=True).returncode,2)


class TransactionTests(unittest.TestCase):
    def test_scan_void_preserves_net_counts(self):
        value=inputs();value['events'].insert(1,{'id':'void','type':'scan_void','scan_id':'scan','t_ms':2000})
        self.assertEqual(validate_inputs(value)['sku'],0)

    def test_double_void_rejected(self):
        value=inputs();value['events'][1:1]=[{'id':f'void{i}','type':'scan_void','scan_id':'scan','t_ms':2000} for i in range(2)]
        with self.assertRaises(ValueError):validate_inputs(value)

    def test_partial_and_out_of_order_streams_rejected(self):
        value=inputs();value['events'].pop()
        with self.assertRaises(ValueError):validate_inputs(value)
        value=inputs();value['events'][0]['t_ms']=4000
        with self.assertRaises(ValueError):validate_inputs(value)

    def test_bad_catalog_and_unknown_sku_rejected(self):
        value=inputs();value['catalog']={'99':'sku'}
        with self.assertRaises(ValueError):validate_inputs(value)
        value=inputs();value['events'][0]['sku']='unknown'
        with self.assertRaises(ValueError):validate_inputs(value)


if __name__ == '__main__':
    unittest.main()
