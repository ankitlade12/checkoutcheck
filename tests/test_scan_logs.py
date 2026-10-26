"""Temporary parser checks; these records are never demonstration data."""
import unittest
from checkoutcheck.scan_logs import parse_events, validate_log


class ScanLogTests(unittest.TestCase):
    def test_csv_keeps_supplied_events_and_units(self):
        text='id,type,t_ms,sku,quantity,scan_id\na,scan_add,100,sku,2,\nb,scan_void,200,,,a\nc,payment_complete,300,,,\n'
        result=validate_log({'content':text,'format':'csv','inputs':{'catalog':{'0':'sku'},'offset_ms':50,'bagging_x':.6,'min_observations':3}})
        self.assertEqual(result['net_scan_counts'],{'sku':0})
        self.assertEqual(result['payment_video_ms'],350)
        self.assertEqual(result['events'][1],{'id':'b','type':'scan_void','t_ms':200,'scan_id':'a'})

    def test_reject_ambiguous_columns_and_time(self):
        for text in ['id,type,t_ms,t_ms\na,payment_complete,1,2','id,type,t_ms\na,payment_complete,0.5','id,type,t_ms\na,payment_complete,1,extra']:
            with self.assertRaises(ValueError):parse_events(text,'csv')

    def test_json_duplicate_fields_rejected(self):
        with self.assertRaises(ValueError):parse_events('[{"id":"a","id":"b"}]','json')

    def test_does_not_create_missing_payment(self):
        with self.assertRaises(ValueError):
            validate_log({'content':'id,type,t_ms,sku,quantity\na,scan_add,100,sku,1','format':'csv','inputs':{'catalog':{'0':'sku'},'offset_ms':0,'bagging_x':.6,'min_observations':3}})
