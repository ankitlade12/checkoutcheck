"""Inspect an actual read-only deployment; never creates evaluation data."""
import os
from playwright.sync_api import sync_playwright, expect

url = os.environ.get('CHECKOUTCHECK_URL', 'http://127.0.0.1:8768').rstrip('/')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHECKOUTCHECK_BROWSER'), headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url, wait_until='networkidle')
    expect(page.locator('#start-perception')).to_be_disabled()
    expect(page.locator('nav [data-page="runs"]')).to_be_hidden()
    assert page.locator('.photo-card').count() == 24
    state = page.request.get(url+'/v1/state').json()
    assert state['runtime']['read_only'] and not state['runs']
    data = page.request.get(url+'/v1/perception').json()
    runs = {r['model']: r for r in data['runs'] if r['status'] == 'completed'}
    agent = runs['vision-agent-v1']
    page.locator('[data-perception-run="'+agent['id']+'"]').click()
    expect(page.get_by_text('Agent task evaluation', exact=True)).to_be_visible()
    page.locator('.photo-card').first.click()
    expect(page.get_by_role('heading', name='Perception → decision → action')).to_be_visible()
    page.locator('#perception-other').select_option(runs['fasterrcnn-rpc-v1']['id'])
    page.get_by_role('button', name='Compare measured results').click()
    expect(page.locator('#perception-comparison table')).to_be_visible()
    page.locator('nav [data-page="videos"]').click()
    page.locator('[data-video-open]').first.click()
    page.locator('#source-video').wait_for()
    page.wait_for_function('() => document.querySelector("#source-video").readyState >= 1')
    for path in ('/v1/assets', '/v1/perception/runs', '/v1/suites'):
        assert page.request.post(url+path, data={}).status == 403
    assert page.request.get(url+'/v1/media/unknown').status == 403
    cool = page.request.get(url+'/v1/cool').json()
    assert cool['available'] and cool['deployment']['instance_type'] == 'c8g.large'
    for name in ('stock', 'cool', 'comparison', 'deployment'):
        assert page.request.get(url+'/v1/cool/'+name).status == 200
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.goto(url+'/demo', wait_until='networkidle')
    page.wait_for_function('() => document.querySelector("video").readyState >= 1')
    assert 0 < page.locator('video').evaluate('(v) => v.duration') <= 300
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.request.get(url+'/licenses/RetailAction-LICENSE.txt').status == 200
    assert not errors, errors
    browser.close()
print('PASS: public HTTPS review, actual agent trace, measured comparison, original video, COOL evidence, narrated demo under five minutes, license copy, blocked writes/private media, mobile layout.')
