"""Record actual public application flows with requested Indian English narration.

Requires macOS say (Rishi), ffmpeg, and Playwright. Title/architecture cards are
presentation graphics; application scenes use the live deployment unchanged.
"""
import html
import json
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path(os.environ.get('CHECKOUTCHECK_RECORDING_DIR', 'artifacts/submission-video')).resolve()
URL = os.environ.get('CHECKOUTCHECK_URL', 'https://d2pt18a0j9tuil.cloudfront.net').rstrip('/')
OUTPUT.mkdir(parents=True, exist_ok=True)
local_browsers = Path('private-data/playwright').resolve()
if (local_browsers/'ffmpeg-1011').exists():
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(local_browsers))

SCENES = [
    ('team', 'The team behind CheckoutCheck',
     'CheckoutCheck. Built by Ankit Hemant Lade and Sai Jasti.'),
    ('problem', 'A camera sees an item. Did the checkout agree?',
     'At self checkout, seeing a product is only half the problem. Was it scanned? Is it the right item? And when the picture is unclear, should a person step in? An unreliable alert can frustrate an honest customer. CheckoutCheck is an open evaluation workbench that helps teams inspect the evidence before trusting a checkout vision system. Let us see the working prototype.'),
    ('detection', 'See the result. Inspect the misses.',
     'This is the application running on AWS. The real data lab compares methods on twenty four original photographs, containing two hundred and ninety one annotated products. Four hundred separate training photographs support the reference bank and detector training. Select a completed run and every score has a denominator. Our trained detector matched one hundred and five products, with seventy four point five percent precision and thirty six point one percent recall. Open an image to inspect orange predictions against blue reference boxes. The missed objects are visible, not hidden behind one headline score.'),
    ('agent', 'Perception changes the next action.',
     'The investigation agent first measures sharpness and foreground structure with OpenCV five. Those observations choose a neural detector or a watershed refinement. Here is the actual decision trace. Across the twenty four images, it selected the neural path eighteen times and watershed six times. Seventeen images were recommended for human inspection. Each image stayed within three tool calls. This is a deterministic controller, not a language model. Its detection recall was lower than the trained detector alone, so the comparison makes that tradeoff explicit. It never takes automatic action against a customer.'),
    ('video', 'Inspect real video, frame by frame.',
     'The real video lab lets a reviewer play original retail clips, seek a source frame, and inspect motion and image quality. Publisher interaction labels remain separate from model output. These shelf clips do not include synchronized checkout scans or payment records. That matters: image detection is not proof of an unpaid item. The next validation step needs consented checkout recordings with matching transaction events and independent review.'),
    ('architecture', 'OpenCV 5 + AWS',
     'The architecture connects a browser workbench to a Python API, a bounded job worker, OpenCV five, and the registered detectors. AWS EC2 performs the evaluation. Private S3 stores approved source inputs and model weights. Evaluation results stay on EC2. Judges reach a separate read only service through CloudFront HTTPS. The operator workspace handles uploads and execution privately. Source hashes, model identifiers, image checksums and reproducible scoring make each result inspectable.'),
    ('cool', 'Measured COOL execution on Graviton.',
     'We also ran the actual foreground and watershed pipelines using the official Cloud Optimized OpenCV image on AWS Graviton. Across five warm batches on the same machine, COOL was about three point three percent faster for foreground processing and four point one percent faster for watershed, with identical evaluation scores. These are modest observed differences. The application links the raw reports, exact runtime versions and deployment configuration, so judges can inspect the evidence.'),
    ('community', 'Better evidence before checkout alerts.',
     'CheckoutCheck gives the community a practical starting point: original data acquisition, comparable baselines, visible failure cases, an auditable agent, and a working cloud review interface. The application source is public under the MIT license; dataset licenses remain separate. This is a research prototype, not a validated theft detector. Our goal is to help developers and retailers build better evidence, preserve human judgment, and test carefully before deploying alerts around real customers.'),
]


def card(title, subtitle, architecture=False):
    flow = ('<div class="flow"><b>Browser workbench</b><span>↓ CloudFront HTTPS</span><b>EC2 · public review</b>'
            '<span>Read-only snapshot ← private API + worker</span><b>OpenCV 5 → detector / agent → evaluation</b>'
            '<span>Private S3 inputs · results remain on EC2</span></div>') if architecture else ''
    return '''<!doctype html><html><head><style>
    *{box-sizing:border-box}body{margin:0;background:#102e29;color:#f4f7ed;font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif}
    main{padding:82px 100px;width:1280px;height:800px;display:flex;flex-direction:column;justify-content:center}
    .brand{font-size:23px;letter-spacing:1px;color:#bbd6ab;margin-bottom:50px}h1{font-size:64px;line-height:1.08;max-width:1050px;margin:0 0 30px;letter-spacing:-2px}
    p{font-size:26px;color:#d1ded2;line-height:1.5;max-width:1000px;margin:0}footer{margin-top:50px;font-size:18px;color:#bbd6ab}
    .flow{display:flex;flex-direction:column;gap:12px;margin:8px 0;font-size:23px}.flow b{background:#23463c;padding:14px 20px;border-left:4px solid #c4de82}.flow span{color:#cfddc8;font-size:19px;padding-left:22px}
    </style></head><body><main><div class="brand">▣ CHECKOUTCHECK</div><h1>'''+html.escape(title)+'''</h1><p>'''+html.escape(subtitle)+'''</p>'''+flow+'''<footer>OpenCV AI Competition 2026 · Powered by AWS</footer></main></body></html>'''


def duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], text=True))


selected_scenes = set(os.environ.get('CHECKOUTCHECK_SCENES', ','.join(s[0] for s in SCENES)).split(','))
for key, _, speech in SCENES:
    if key not in selected_scenes: continue
    (OUTPUT/(key+'.txt')).write_text(speech+'\n')
    subprocess.run(['say', '-v', 'Rishi', '-r', '155', '-f', str(OUTPUT/(key+'.txt')), '-o', str(OUTPUT/(key+'.aiff'))], check=True)
(OUTPUT/'narration.json').write_text(json.dumps(SCENES, indent=2)+'\n')

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHECKOUTCHECK_BROWSER'), headless=True)
    for key, title, _ in SCENES:
        if key not in selected_scenes: continue
        context = browser.new_context(viewport={'width': 1280, 'height': 800}, record_video_dir=str(OUTPUT/key), record_video_size={'width':1280,'height':800})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        started = time.monotonic()
        length = duration(OUTPUT/(key+'.aiff'))+2
        if key in ('team', 'problem', 'architecture', 'community'):
            subtitles = {'team':'Ankit Hemant Lade · Sai Jasti', 'problem':'Inspect what the camera sees. Measure what the system misses.',
                         'architecture':'Measured inference · auditable decisions · human inspection',
                         'community':'github.com/ankitlade12/checkoutcheck\nOriginal data. Reproducible scores. Visible limitations.'}
            page.set_content(card(title, subtitles[key], key=='architecture'))
        else:
            page.goto(URL+'/#'+('videos' if key=='video' else 'perception'), wait_until='networkidle')
            if key in ('detection','agent'):
                data = page.request.get(URL+'/v1/perception').json()
                model = 'vision-agent-v1' if key=='agent' else 'fasterrcnn-rpc-v1'
                run = next(r for r in data['runs'] if r['model']==model and r['status']=='completed')
                page.wait_for_timeout(3000)
                page.locator('[data-perception-run="'+run['id']+'"]').click()
                page.locator('#perception-result').scroll_into_view_if_needed()
                page.wait_for_timeout(9000)
                if key=='agent':
                    page.get_by_text('Agent task evaluation', exact=True).click()
                    page.get_by_text('Agent task evaluation', exact=True).scroll_into_view_if_needed()
                    page.wait_for_timeout(7000)
                page.locator('.photo-card').first.click()
                page.locator('#rpc-detail-image').scroll_into_view_if_needed()
                page.wait_for_timeout(7000)
                if key=='agent':
                    page.get_by_role('heading', name='Perception → decision → action').scroll_into_view_if_needed()
                else:
                    page.locator('#show-reference').uncheck()
                    page.wait_for_timeout(4000)
                    page.locator('#show-reference').check()
            elif key=='cool':
                page.locator('#cool-results').scroll_into_view_if_needed()
            else:
                page.wait_for_timeout(4000)
                page.locator('[data-video-open]').first.click()
                page.locator('#source-video').scroll_into_view_if_needed()
                page.locator('#source-video').evaluate('(v)=>{v.muted=true; return v.play()}')
                page.wait_for_timeout(6000)
                page.locator('[data-video-frame="16"]').click()
                page.locator('#source-time-display').scroll_into_view_if_needed()
        page.wait_for_timeout(max(1000, (length-(time.monotonic()-started))*1000))
        assert not errors, errors
        video = page.video
        context.close()
        video.save_as(str(OUTPUT/(key+'.webm')))
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(OUTPUT/(key+'.webm')),'-i',str(OUTPUT/(key+'.aiff')),
                        '-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-af','apad',
                        '-shortest','-movflags','+faststart',str(OUTPUT/(key+'.mp4'))],check=True)
        print('Recorded '+key, flush=True)
    browser.close()

(OUTPUT/'concat.txt').write_text(''.join("file '"+key+".mp4'\n" for key, _, _ in SCENES))
final = OUTPUT/'checkoutcheck-product-demo.mp4'
subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(OUTPUT/'concat.txt'),'-c','copy','-movflags','+faststart',str(final)],check=True)
assert duration(final) <= 300, 'Submission video exceeds five minutes'
print(json.dumps({'video':str(final),'duration_seconds':duration(final),'voice':'Rishi, English (India)','team_credits':['Ankit Hemant Lade','Sai Jasti'],'live_team_footage':False}))
