"""Acquire original publisher videos, without creating transaction labels."""
import argparse
import hashlib
import json
import re
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .evaluator import digest, require

SOURCE='https://huggingface.co/datasets/standard-cognition/RetailAction'


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquire(directory, groups=3):
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.json').exists():
        manifest=load_manifest(root)
        for entry in manifest['files']:
            require(checksum(root/entry['path'])==entry['sha256'],'Original video dataset checksum mismatch')
        print(f"Verified {len(manifest['videos'])} original videos",flush=True)
        return manifest
    require(type(groups) is int and 1<=groups<=10,'Select 1–10 original dual-view groups')
    with urllib.request.urlopen('https://huggingface.co/api/datasets/standard-cognition/RetailAction',timeout=30) as response:
        revision=json.load(response)['sha']
    require(bool(re.fullmatch('[0-9a-f]{40}',revision)),'Invalid publisher revision')
    base=SOURCE+'/resolve/'+revision+'/'
    for name in ['LICENSE','README.md']:
        with urllib.request.urlopen(base+name,timeout=30) as response:
            raw=response.read(100_001)
        require(len(raw)<=100_000,'Source document exceeds limit')
        (root/name).write_bytes(raw)
    archive_url=base+'data/validation.tar'
    selected=[]
    files=[]
    complete={}
    with urllib.request.urlopen(archive_url,timeout=60) as response:
        with tarfile.open(fileobj=response,mode='r|') as archive:
            for member in archive:
                if not member.isfile():continue
                match=re.fullmatch(r'validation/(\d{6})/(rank[01]_video\.mp4|metadata\.json)',member.name)
                if not match:continue
                group,name=match.groups()
                if group not in selected:
                    if len(selected)>=groups:continue
                    selected.append(group)
                    complete[group]=set()
                require(0<member.size<=20_000_000,'Source member exceeds size limit')
                raw=archive.extractfile(member).read(member.size+1)
                require(len(raw)==member.size,'Incomplete source download')
                relative=f'{group}/{name}'
                target=root/relative
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(raw)
                files.append({'path':relative,'source_member':member.name,'sha256':checksum(target),'bytes':len(raw)})
                complete[group].add(name)
                print(f'Downloaded original {relative}',flush=True)
                if len(selected)==groups and all(len(names)==3 for names in complete.values()):break
    require(len(selected)==groups and all(len(names)==3 for names in complete.values()),'Incomplete original video groups')
    manifest={'schema_version':'retail-video/1.0','dataset':'RetailAction','publisher':'Standard Cognition',
              'source':SOURCE,'revision':revision,'source_archive':archive_url,'source_split':'validation',
              'evidence_kind':'real_camera_recordings','selection':'First complete dual-view groups in the publisher archive; exploratory convenience sample',
              'license':'Standard.AI Dataset License','license_sha256':checksum(root/'LICENSE'),
              'files':files,'videos':[{'id':e['path'].replace('/','-').removesuffix('.mp4'),**e} for e in files if e['path'].endswith('.mp4')],
              'limitations':['Shelf interactions, not a synchronized POS/payment benchmark.',
                             'Publisher clips use selected frames; original metadata timestamps must be preserved.',
                             'No scan logs, transaction truth, discrepancy labels or demographic inferences are created.',
                             'Local research use with publisher attribution; no public release is performed.']}
    manifest['hash']=digest(manifest)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (root/'NOTICE.txt').write_text('This Dataset is licensed under the Standard.AI Dataset License, Copyright © Standard Corp. All Rights Reserved.\nOriginal source: '+SOURCE+'\nNo synthetic videos or transaction events.\n')
    return manifest


def load_manifest(directory):
    root=Path(directory)
    manifest=json.loads((root/'manifest.json').read_text())
    require(manifest.get('schema_version')=='retail-video/1.0','Unsupported video manifest')
    require(digest({k:v for k,v in manifest.items() if k!='hash'})==manifest['hash'],'Video manifest integrity failure')
    for entry in manifest['files']:
        require(bool(re.fullmatch(r'\d{6}/(rank[01]_video\.mp4|metadata\.json)',entry['path'])),'Unsafe video path')
    return manifest


def analyze(directory, identifier):
    import cv2
    root=Path(directory)
    manifest=load_manifest(root)
    entry=next((v for v in manifest['videos'] if v['id']==identifier),None)
    require(entry is not None,'Unknown registered video')
    path=root/entry['path']
    require(checksum(path)==entry['sha256'],'Video checksum mismatch')
    group,camera=entry['path'].split('/')
    metadata_path=f'{group}/metadata.json'
    metadata_entry=next(f for f in manifest['files'] if f['path']==metadata_path)
    require(checksum(root/metadata_path)==metadata_entry['sha256'],'Publisher annotation checksum mismatch')
    metadata=json.loads((root/metadata_path).read_text())['content']
    camera=camera.removesuffix('_video.mp4')
    def timestamp(value):
        parsed=datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    start=timestamp(metadata['segment_info']['sampled_at_start'])
    duration=timestamp(metadata['segment_info']['sampled_at_end'])-start
    require(duration>0,'Invalid source segment duration')
    source_times=[timestamp(t)-start for t in metadata['action_cam'][camera]['frame_timestamps']]
    require(source_times and all(b>=a for a,b in zip(source_times,source_times[1:])),'Source timestamps are not monotonic')
    capture=cv2.VideoCapture(str(path))
    require(capture.isOpened(),'Original video cannot be decoded')
    fps=capture.get(cv2.CAP_PROP_FPS)
    require(0<fps<=60,'Unsupported encoded frame rate')
    frames=[]
    previous=None
    try:
        while True:
            ok,frame=capture.read()
            if not ok:break
            index=len(frames)
            require(index<len(source_times) and index<120,'Frame count does not agree with publisher timestamps')
            require(max(frame.shape[:2])<=1920,'Unsupported source resolution')
            gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            small=cv2.resize(gray,(320,320),interpolation=cv2.INTER_AREA)
            fraction=float((cv2.absdiff(small,previous)>25).mean()) if previous is not None else None
            frames.append({'index':index,'playback_seconds':index/fps,'source_seconds':source_times[index],
                           'changed_pixel_fraction':fraction,'laplacian_variance':float(cv2.Laplacian(gray,cv2.CV_64F).var())})
            previous=small
        require(len(frames)==len(source_times),'Video is truncated or source timestamp mapping is incomplete')
    finally:capture.release()
    annotations=[]
    for action in metadata['labels']['action']:
        require(0<=action['start']<=action['end']<=1,'Invalid publisher action interval')
        annotations.append({'label':action['label'],'source_start_seconds':action['start']*duration,
                            'source_end_seconds':action['end']*duration,'position':action['spatial']['action_cam'][camera]})
    result={'schema_version':'retail-video-analysis/1.0','video_id':identifier,'dataset_hash':manifest['hash'],
            'source_sha256':entry['sha256'],'annotation_sha256':metadata_entry['sha256'],
            'frames':frames,'fps':fps,'playback_duration_seconds':len(frames)/fps,'source_duration_seconds':duration,
            'publisher_annotations':annotations,'opencv_version':cv2.__version__,'code_sha256':checksum(__file__),
            'method':{'id':'frame-difference-v1','resize':[320,320],'absolute_difference_threshold':25},
            'limitations':manifest['limitations']+['Motion and sharpness are diagnostics, not predicted actions, product identities or payment discrepancies.']}
    (root/'analysis').mkdir(exist_ok=True)
    target=root/'analysis'/f'{identifier}.json'
    temporary=target.with_suffix('.part')
    temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    temporary.replace(target)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='private-data/retailaction')
    parser.add_argument('--groups',type=int,default=3)
    parser.add_argument('--analyze',help='Analyze a registered video ID, or all')
    args=parser.parse_args()
    if args.analyze:
        identifiers=[v['id'] for v in load_manifest(args.directory)['videos']] if args.analyze=='all' else [args.analyze]
        results=[analyze(args.directory,identifier) for identifier in identifiers]
        print(json.dumps(results if args.analyze=='all' else results[0]))
    else:
        result=acquire(args.directory,args.groups)
        print(json.dumps({'videos':len(result['videos']),'manifest_hash':result['hash']}))
