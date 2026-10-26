"""Hand-calculated timeline checks in memory; no recordings or app data created."""
import subprocess
import unittest
from pathlib import Path


class EvidenceTimelineTests(unittest.TestCase):
    def test_imported_and_unmatched_alerts_remain_visible(self):
        script='''
const assert=require('node:assert/strict');
const {evidenceTimeline}=require('./apps/web/evidence.js');
const entry={inputs:{offset_ms:50,events:[{id:'scan',type:'scan_add',t_ms:100,sku:'a'}]},annotation:{discrepancies:[{sku:'a',start_ms:200,end_ms:400}]}};
const alerts=[{id:'matched',sku:'a',t_ms:250},{id:'unmatched',sku:'b',t_ms:500}];
const timeline=evidenceTimeline(entry,alerts,[{prediction_id:'matched'}]);
assert.deepEqual(timeline.map(e=>e.t_ms),[150,200,250,400,500]);
assert(timeline[2].label.includes('matched reference'));
assert(timeline[4].label.includes('unmatched alert'));
assert.equal(evidenceTimeline(entry,alerts,[]).filter(e=>e.label.includes('unmatched alert')).length,2);
'''
        result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
