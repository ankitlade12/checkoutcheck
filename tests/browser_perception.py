"""Exercise the installed original RPC dataset through the actual local server."""
import json
import os
from pathlib import Path
BASE_URL = os.environ.get('CHECKOUTCHECK_URL', 'http://127.0.0.1:8765').rstrip('/')

from playwright.sync_api import sync_playwright, expect

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('CHECKOUTCHECK_BROWSER'))
    page = browser.new_page(viewport={'width':1440,'height':1100})
    errors = []
    failed_responses = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: failed_responses.append(f'{response.status} {response.url}') if response.status >= 400 else None)
    page.goto(BASE_URL+'/#perception', wait_until='networkidle')
    page.get_by_role('heading', name='Real-data lab', exact=True).wait_for()
    page.locator('.photo-card').first.wait_for()
    assert page.locator('.photo-card').count() == 24
    # Click through actual inference, persistence and polling; no injected results.
    created = []
    for model in os.environ.get('CHECKOUTCHECK_MODELS', 'foreground-components-v1,watershed-v1,sift-reference-v1,fasterrcnn-coco-v1,fasterrcnn-rpc-v1').split(','):
        page.locator('#perception-model').select_option(model)
        with page.expect_response(lambda response: response.url.endswith('/v1/perception/runs') and response.request.method == 'POST') as queued:
            page.locator('#start-perception').click()
        assert queued.value.status == 202
        identifier = queued.value.json()['id']
        created.append(identifier)
        expect(page.locator('#perception-result .badge')).to_have_text('completed', timeout=660000)
        result = page.request.get(BASE_URL+'/v1/runs/'+identifier).json()
        assert result['result']['adapter']['id'] == model
        assert result['result']['report']['metrics']['scored_images'] == 24
        page.reload(wait_until='networkidle')
        expect(page.locator(f'[data-perception-run="{identifier}"]')).to_be_visible()
    # Cancel a real running worker through the UI and ensure it publishes no result.
    page.locator('#perception-model').select_option('sift-reference-v1')
    with page.expect_response(lambda response: response.url.endswith('/v1/perception/runs') and response.request.method == 'POST') as queued:
        page.locator('#start-perception').click()
    canceled_id = queued.value.json()['id']
    expect(page.locator('#perception-result .badge')).to_have_text('running', timeout=30000)
    page.get_by_role('button', name='Cancel run', exact=True).click()
    expect(page.locator('#perception-result .badge')).to_have_text('canceled')
    canceled = page.request.get(BASE_URL+'/v1/runs/'+canceled_id).json()
    assert canceled['status'] == 'canceled' and canceled['result'] is None
    data = page.request.get(BASE_URL+'/v1/perception').json()
    runs = [r for r in data['runs'] if r['status']=='completed']
    assert len(runs) >= 2, 'Complete at least two real-data runs first'
    sift = next(r for r in runs if r['model']=='sift-reference-v1')
    page.locator(f'[data-perception-run="{sift["id"]}"]').click()
    page.get_by_role('heading', name='Results by difficulty').wait_for()
    assert '24/24 images scored' in page.locator('#perception-result').inner_text()
    page.locator('#perception-other').select_option(next(r['id'] for r in runs if r['id']!=sift['id']))
    page.get_by_role('button', name='Compare measured results').click()
    page.locator('#perception-comparison table').wait_for()
    page.locator('.photo-card').first.click()
    image = page.locator('#rpc-detail-image')
    image.wait_for()
    expected_width = data['manifest']['images'][0]['width']
    page.wait_for_function('(width) => document.querySelector("#rpc-detail-image").naturalWidth === width', arg=expected_width)
    assert page.locator('#rpc-boxes').evaluate('(c) => c.width') == expected_width
    page.locator('#show-reference').uncheck()
    page.locator('#show-reference').check()
    with page.expect_download() as download:
        page.get_by_role('link', name='Export scoring evidence').click()
    download.value.save_as('artifacts/rpc-browser-export.json')
    assert json.loads(Path('artifacts/rpc-browser-export.json').read_text())['kind']=='rpc_perception'
    page.screenshot(path='artifacts/rpc-lab-desktop.png', full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
    page.screenshot(path='artifacts/rpc-lab-mobile.png', full_page=True)
    assert not errors, errors
    assert not failed_responses, failed_responses
    print(json.dumps({'real_images':24,'new_completed_runs':created,'browser_execution':'passed','reload_persistence':'passed','running_worker_cancellation':'passed','inspect':'passed','overlays':'passed','comparison':'passed','export':'passed','mobile_overflow':False,'browser_errors':errors,'failed_http_responses':failed_responses}))
    browser.close()
