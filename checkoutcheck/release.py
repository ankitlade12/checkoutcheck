"""Package actual local evidence and source for private hackathon review."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

from .perception import verify_result
from .evaluator import require


def package(root, output):
    root=Path(root).resolve()
    output=Path(output).resolve()
    require(not output.exists(),'Use a new output directory to preserve previous releases')
    checks=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=root,capture_output=True,text=True)
    require(checks.returncode==0,'Software checks failed; do not package a release')
    for file in ['app.js','perception.js','videos.js','evidence.js']:
        checked=subprocess.run(['node','--check',str(root/'apps/web'/file)],capture_output=True,text=True)
        require(checked.returncode==0,f'JavaScript syntax check failed: {file}')
    output.mkdir(parents=True)
    (output/'software-checks.txt').write_text(checks.stdout+checks.stderr)
    data=root/'private-data'
    results={}
    with sqlite3.connect(data/'workbench.sqlite') as connection:
        for raw, in connection.execute("SELECT result FROM runs WHERE status IN ('completed','partial') AND json_extract(data,'$.task')='rpc_perception' ORDER BY created DESC"):
            result=json.loads(raw)
            verify_result(result)
            results.setdefault(result['adapter']['id'],result)
    require(bool(results),'Run a real-image benchmark before creating the evidence package')
    evidence=output/'evidence'
    evidence.mkdir()
    for model,result in results.items():
        (evidence/f'{model}.json').write_text(json.dumps(result,indent=2)+'\n')
    video_files=list((data/'retailaction/analysis').glob('*.json'))
    for file in video_files:(evidence/('video-'+file.name)).write_bytes(file.read_bytes())
    notices=output/'source-notices'
    notices.mkdir()
    for source,target in [(data/'rpc/NOTICE.txt','RPC-NOTICE.txt'),(data/'retailaction/LICENSE','RetailAction-LICENSE.txt'),(data/'retailaction/NOTICE.txt','RetailAction-NOTICE.txt')]:
        if source.exists():(notices/target).write_bytes(source.read_bytes())
    model_manifest=data/'models/rpc-fasterrcnn-v1/manifest.json'
    if model_manifest.exists():(evidence/'training-provenance.json').write_bytes(model_manifest.read_bytes())
    cloud_path=data/'aws-verification.json'
    cloud=json.loads(cloud_path.read_text()) if cloud_path.exists() else None
    if cloud and cloud.get('verified') is True:
        (evidence/'aws-verification.json').write_text(json.dumps(cloud,indent=2)+'\n')
        for name in ('smoke','videos','perception'):
            check=root/f'artifacts/aws-{name}-verification.txt'
            (evidence/check.name).write_bytes(check.read_bytes())
        for file in sorted((root/'artifacts/aws-evidence').glob('*.json')):
            result=json.loads(file.read_text())
            if result.get('kind')=='rpc_perception':
                verify_result(result)
                (evidence/('aws-'+file.name)).write_bytes(file.read_bytes())
    # Submission documents share the reviewed repository source of truth.
    for name in ('technical-report.md','architecture.mmd','architecture.svg','workflow.mmd','workflow.svg','agentic-vision.md','cool-evaluation.md'):
        source=root/'docs'/name
        if source.is_file():(output/name).write_bytes(source.read_bytes())
    (output/'demo-script.md').write_text('The reproducible product-demo recorder is tests/record_submission_demo.py. It uses Indian English male narration and actual AWS application scenes. Opening credits identify Ankit Hemant Lade and Sai Jasti. No live team footage is included; organizer acceptance of name credits is not confirmed.\n')
    (output/'README.md').write_text('Read technical-report.md and the source README. The AWS judge endpoint is https://d2pt18a0j9tuil.cloudfront.net. Agent and COOL evidence are available there. This package is prepared for review; Devpost submission is not implied. The video identifies team members by name; live team footage is not included.\n')
    with zipfile.ZipFile(output/'checkoutcheck-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        roots=['checkoutcheck','apps/web','tests','docs','infra','.github']
        files=[root/name for name in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md','pyproject.toml','requirements.lock','compose.yaml','run.command','start-aws.command','.dockerignore','.gitignore']]
        for directory in roots:files.extend((root/directory).rglob('*'))
        for file in sorted(files):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix not in {'.pyc','.mp4','.jpg','.pth'}:
                archive.write(file,file.relative_to(root))
    manifest={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(output),'files':len(manifest),'verified_model_reports':len(results),'original_video_analyses':len(video_files)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    package(args.root,args.output)
