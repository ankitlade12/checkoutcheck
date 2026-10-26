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
    rows=[]
    for model,result in results.items():
        (evidence/f'{model}.json').write_text(json.dumps(result,indent=2)+'\n')
        m=result['report']['metrics']
        percent=lambda value:'N/A' if value is None else f'{100*value:.2f}%'
        rows.append(f"| {result['adapter']['name']} | {m['scored_images']}/{m['submitted_images']} | {m['true_positive']}/{m['reference_objects']} | {percent(m['precision'])} | {percent(m['recall'])} | {m['count_mae']:.2f} |")
    video_files=list((data/'retailaction/analysis').glob('*.json'))
    for file in video_files:(evidence/('video-'+file.name)).write_bytes(file.read_bytes())
    notices=output/'source-notices'
    notices.mkdir()
    for source,target in [(data/'rpc/NOTICE.txt','RPC-NOTICE.txt'),(data/'retailaction/LICENSE','RetailAction-LICENSE.txt'),(data/'retailaction/NOTICE.txt','RetailAction-NOTICE.txt')]:
        if source.exists():(notices/target).write_bytes(source.read_bytes())
    model_manifest=data/'models/rpc-fasterrcnn-v1/manifest.json'
    if model_manifest.exists():(evidence/'training-provenance.json').write_bytes(model_manifest.read_bytes())
    report='''# CheckoutCheck — hackathon technical report

Status: local engineering demonstration. AWS execution and final submission are not complete.

## Problem and users

Checkout vision engineers need to inspect errors against real evidence and distinguish visual observations, reference annotations and transaction truth. CheckoutCheck supports reproducible, offline evaluation without identity inference, intent scoring or live enforcement. The intended community benefit is inspectable evidence and honest failure reporting; reduced shopper harm has not been demonstrated.

## Working implementation

The login-free, single-operator application serves a real-image benchmark and original-video inspection workflow. FastAPI and SQLite persist runs. OpenCV 5 decodes images/video, extracts SIFT and classical regions, computes video diagnostics and evaluates marker-instrumented transaction recordings when actual POS evidence is supplied. PyTorch executes the Faster R-CNN network; it is not misrepresented as OpenCV DNN inference.

The real-photo detector was fine-tuned on 400 original RPC training photos for two epochs, with no fine-tuning augmentation, rendering or compositing. Its 24 evaluation photos are disjoint. The upstream torchvision checkpoint has documented COCO/ImageNet photographic training provenance; that documentation is not an independent audit of every upstream image.

## Actual image measurements

Box matching uses one-to-one IoU >= 0.5. These are exploratory sample results, not a population or leaderboard claim. Exported reports contain exact denominators, misses, configs, build/source hashes and predictions.

| Method | Images scored | Matched objects | Precision | Recall | Count MAE |
| --- | --- | --- | --- | --- | --- |
'''+ '\n'.join(rows)+f'''

## Original videos

{len(video_files)} original RetailAction clip analyses are included. Source footage is publisher-anonymized and uses selected frames; encoded playback time and source timestamps are mapped separately. Publisher interaction points are labels, not model predictions. Motion and sharpness are diagnostics, not evidence of a scan, payment or discrepancy. No POS histories were manufactured.

## Architecture and AWS status

See architecture.mmd. The working path is browser → FastAPI → SQLite queue → bounded local worker → original evidence → evaluator → stored/exported results. The proposed private AWS path uses EC2, private encrypted S3, restricted IAM, Session Manager port forwarding and CloudWatch logs. This package contains no verified AWS execution record unless evidence/aws-verification.json is included. Configure and verify your own deployment using the operations guide. No AWS, COOL or Agentic Vision award eligibility is claimed.

## Verification

software-checks.txt records the actual checks executed while creating this package. Real-data browser scripts cover model execution, saved results, cancellation, video playback/seeking, comparison and export. Run them against installed licensed originals; CI software checks alone do not establish real transaction performance. Image report scores are recomputed before packaging.

## Limits and responsible use

The detector still misses many products. The neural detector does not recognize SKUs; SIFT SKU matching is weak. Public source videos do not supply synchronized POS or independently verified checkout outcomes, so the transaction workflow remains unvalidated end to end. Access is private and single-operator; no application login is required for the hackathon scope, and this app must not be exposed as a public write endpoint. Multi-user collaboration, independent reviewer identities and production retention controls are deferred.

The package includes source and diagnostic/annotation metadata, not original media, model weights, credentials or private transaction recordings. Preserve the source-notices licenses. RPC is noncommercial/share-alike; RetailAction uses its custom license. Publication/commercial rights are not inferred from download access.

## Submission items still requiring completion

- Successful real OpenCV workload on AWS, with execution logs and artifact hashes.
- Team identity/bio and a real team introduction for the video.
- Judge-accessible archive/repository or arranged live screen share.
- Final public/unlisted video under five minutes, reviewed for source-media rights.
- Submission and eligibility review against the current organizer rules.

## Sources

- Competition: https://opencv26.devpost.com/
- RPC: https://rpc-dataset.github.io/
- RetailAction: https://huggingface.co/datasets/standard-cognition/RetailAction
- Torchvision recipe: https://github.com/pytorch/vision/tree/main/references/detection
'''
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
        report=report.replace('Status: local engineering demonstration. AWS execution and final submission are not complete.',
                              'Status: local and private AWS engineering demonstration. Final submission is not complete.')
        start=report.index('See architecture.mmd.')
        end=report.index('\n\n## Verification',start)
        report=report[:start]+('See architecture.mmd and evidence/aws-verification.json. The personal-account deployment uses private EC2, encrypted S3, a scoped instance role, Session Manager and CloudWatch logs. Five real-image methods and six original-video workflows passed cloud browser checks. Source/model hashes and measured cloud reports are included. This is not a production or transaction-accuracy certification; no award eligibility is claimed.')+report[end:]
        report=report.replace('- Successful real OpenCV workload on AWS, with execution logs and artifact hashes.\n','')
    (output/'technical-report.md').write_text(report)
    (output/'architecture.mmd').write_text('''flowchart LR
    Browser[Private browser, no app login] --> API[FastAPI]
    API --> DB[(SQLite queue and results)]
    DB --> Worker[Bounded single worker]
    Originals[Original licensed photos and video] --> Worker
    Worker --> CV[OpenCV 5 preprocessing and diagnostics]
    CV --> Neural[Optional PyTorch detector]
    CV --> Eval[Deterministic evaluator]
    Neural --> Eval
    Eval --> DB
    DB --> Export[Reproducible evidence exports]
    subgraph Proposed_AWS_not_deployed
      SSM[IAM-authorized Session Manager tunnel] --> EC2[EC2 private application port]
      EC2 --> S3[(Private encrypted S3)]
      EC2 --> Logs[CloudWatch logs]
    end
''')
    (output/'demo-script.md').write_text('''# Under-five-minute demonstration outline

0:00–0:20 — Real team introduction, problem and intended users. Record this with the actual team; do not fabricate identities.
0:20–1:25 — Open Real-data lab. Show original-source attribution and the five measured methods. Inspect fine-tuned Faster R-CNN and SIFT; explain precision, recall and missed objects.
1:25–2:15 — Open a real image. Toggle publisher boxes and model predictions. Show a missed object and a false detection. Compare methods on the exact same dataset.
2:15–3:05 — Open Real-video lab. Play an original clip, seek a source frame, show publisher interaction labels and the source/playback timestamp difference. Explain that these are shelf clips with no POS/payment truth.
3:05–3:40 — Export and verify a scoring report. Show the actual software checks and source/model hashes.
3:40–4:20 — Explain the architecture. Show real AWS logs only after a cloud job succeeds; until then label deployment pending.
4:20–4:45 — State limits and next evidence needed. No production, shopper-impact, novelty or award claim without support.
''')
    (output/'README.md').write_text('''# Private judge-review package

Read technical-report.md first. The source archive excludes datasets, weights, credentials and local databases. Recreate the pinned environment and acquire licensed originals using the source README. Evidence JSON verifies scoring without cloud credentials; rerunning inference requires the original data and model.

This is a prepared local package, not an uploaded or accepted competition submission. AWS execution and the human team/video/judge-access steps remain pending.
''')
    if cloud and cloud.get('verified') is True:
        diagram=output/'architecture.mmd'
        diagram.write_text(diagram.read_text().replace('Proposed_AWS_not_deployed','Verified_private_AWS'))
        readme=output/'README.md'
        readme.write_text(readme.read_text().replace('AWS execution and the human team/video/judge-access steps remain pending.', 'AWS execution evidence is included. The human team/video/judge-access steps remain pending.'))
    with zipfile.ZipFile(output/'checkoutcheck-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        roots=['checkoutcheck','apps/web','tests','docs','infra','.github']
        files=[root/name for name in ['README.md','LICENSE','CONTRIBUTING.md','SECURITY.md','THIRD_PARTY_NOTICES.md','pyproject.toml','requirements.lock','compose.yaml','run.command','start-aws.command','.dockerignore','.gitignore']]
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
