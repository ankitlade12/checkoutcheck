"""Parse supplied scan logs; never infer or generate transaction events."""
import csv
import io
import json
import re

from .evaluator import require
from .vision import validate_inputs


def parse_events(content, format):
    require(isinstance(content,str) and len(content.encode('utf-8'))<=1_000_000,'Scan log must be at most 1 MB')
    if format=='json':
        def unique(pairs):
            result={}
            for key,value in pairs:
                require(key not in result,f'Duplicate field: {key}')
                result[key]=value
            return result
        try:events=json.loads(content,object_pairs_hook=unique)
        except json.JSONDecodeError as error:raise ValueError(f'Invalid JSON at line {error.lineno}') from None
    elif format=='csv':
        reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')),strict=True)
        fields=reader.fieldnames
        require(fields is not None and len(fields)==len(set(fields)),'CSV requires unique column headers')
        require({'id','type','t_ms'}<=set(fields)<= {'id','type','t_ms','sku','quantity','scan_id'},'CSV columns: id,type,t_ms,sku,quantity,scan_id; id,type,t_ms are required')
        events=[]
        try:
            for line,row in enumerate(reader,2):
                require(None not in row and all(v is not None for v in row.values()),f'CSV line {line}: wrong number of columns')
                event={k:v.strip() for k,v in row.items() if v.strip()}
                for field in ['t_ms','quantity']:
                    if field in event:
                        require(bool(re.fullmatch(r'\d+',event[field])),f'CSV line {line}: {field} must be an integer; timestamps use milliseconds')
                        event[field]=int(event[field])
                events.append(event)
                require(len(events)<=1000,'Maximum 1000 scan events')
        except csv.Error as error:raise ValueError(f'Invalid CSV: {error}') from None
    else:raise ValueError('Choose json or csv')
    require(isinstance(events,list) and 1<=len(events)<=1000,'Provide 1–1000 recorded events')
    return events


def validate_log(value):
    events=parse_events(value['content'],value['format'])
    inputs={**value['inputs'],'events':events}
    counts=validate_inputs(inputs)
    return {'events':events,'net_scan_counts':dict(counts),'event_count':len(events),
            'payment_video_ms':events[-1]['t_ms']+inputs['offset_ms'],
            'note':'Validated supplied events only; physical inventory and transaction truth must be independently reviewed.'}
