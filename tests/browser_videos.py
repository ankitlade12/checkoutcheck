"""Verify original internet videos through the real local application."""
import json
import os
from pathlib import Path
BASE_URL = os.environ.get('CHECKOUTCHECK_URL', 'http://127.0.0.1:8765').rstrip('/')

from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHECKOUTCHECK_BROWSER'))
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    failed=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('response',lambda response:failed.append(f'{response.status} {response.url}') if response.status>=400 else None)
    page.goto(BASE_URL+'/#videos',wait_until='networkidle')
    expect(page.get_by_role('heading',name='Real-video lab',exact=True)).to_be_visible()
    data=page.request.get(BASE_URL+'/v1/videos').json()
    assert len(data['videos'])==6
    decoded_frames=0
    for entry in data['videos']:
        page.locator(f'[data-video-open="{entry["id"]}"]').click()
        expect(page.locator('#analyze-video')).to_be_visible()
        page.wait_for_function('() => document.querySelector("#source-video").readyState >= 2')
        assert page.locator('#source-video').evaluate('(v)=>v.videoWidth>0 && v.duration>0')
        with page.expect_response(lambda r:r.url.endswith('/analyze') and r.request.method=='POST') as response:
            page.locator('#analyze-video').click()
        assert response.value.status==200
        analysis=response.value.json()
        assert 1<=len(analysis['frames'])<=32
        decoded_frames+=len(analysis['frames'])
        expect(page.locator('#analyze-video')).to_be_enabled()
        middle=len(analysis['frames'])//2
        page.locator(f'[data-video-frame="{middle}"]').click()
        page.wait_for_function('(time)=>Math.abs(document.querySelector("#source-video").currentTime-time)<0.1',arg=analysis['frames'][middle]['playback_seconds'])
        page.locator('#show-video-annotation').uncheck()
        page.locator('#show-video-annotation').check()
        if analysis['publisher_annotations']:
            page.locator('[data-source-action]').first.click()
        else:
            expect(page.get_by_text('No publisher action annotation is present for this clip.')).to_be_visible()
        page.locator('#source-video').evaluate('(v)=>v.play()')
        page.wait_for_timeout(250)
        page.locator('#source-video').evaluate('(v)=>v.pause()')
        range_response=page.request.get(f'{BASE_URL}/v1/videos/{entry["id"]}/media',headers={'Range':'bytes=0-99'})
        assert range_response.status==206 and len(range_response.body())==100
    with page.expect_download() as downloaded:
        page.get_by_role('link',name='Export video diagnostics').click()
    downloaded.value.save_as('artifacts/video-browser-export.json')
    exported=json.loads(Path('artifacts/video-browser-export.json').read_text())
    assert exported['source_sha256']==data['videos'][-1]['sha256']
    page.screenshot(path='artifacts/real-video-lab-desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='artifacts/real-video-lab-mobile.png',full_page=True)
    assert not errors,errors
    assert not failed,failed
    print(json.dumps({'original_videos':6,'decoded_frames':decoded_frames,'playback':'passed','frame_seeking':'passed','source_timestamps':'passed','diagnostics':'passed','range_requests':'passed','export':'passed','mobile_overflow':False,'javascript_errors':errors,'failed_requests':failed}))
    browser.close()
