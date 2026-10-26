"""Browser checks against an empty local workspace; no dataset is created."""
import json
import os
from pathlib import Path
BASE_URL = os.environ.get('CHECKOUTCHECK_URL', 'http://127.0.0.1:8765').rstrip('/')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHECKOUTCHECK_BROWSER'))
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("heading", name="A clearer view of checkout.").wait_for()
    assert page.locator('#overview-stats .stat-value').all_text_contents() == ['0','0','0','0']
    page.screenshot(path="artifacts/checkoutcheck-desktop.png", full_page=True)
    page.get_by_role('button', name='＋ Add real footage').filter(visible=True).click()
    page.get_by_role('dialog').wait_for()
    assert page.get_by_role('textbox',name='Case title').is_visible()
    assert page.locator('#scan-log-file').is_visible()
    assert page.get_by_role('button',name='Validate supplied scan log').is_visible()
    page.get_by_role('button',name='Close dialog').click()
    for label in ('Scenario suites','Evaluation runs','Evidence library','Compare runs','Setup & requirements','Real-data lab','Real-video lab'):
        page.locator('nav').get_by_role('link',name=label).click()
        page.get_by_role('heading',name=label,exact=True).wait_for()
    page.goto(BASE_URL+'/#runs')
    page.get_by_role('button',name='▷ New evaluation').click()
    page.get_by_role('heading',name='Freeze a suite first').wait_for()
    page.keyboard.press('Escape')
    page.set_viewport_size({'width':390,'height':844})
    page.goto(BASE_URL+'/#overview',wait_until='networkidle')
    page.screenshot(path='artifacts/checkoutcheck-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow'
    assert not errors, errors
    print(json.dumps({'browser_errors':errors,'empty_workspace':True,'navigation':'passed','import_dialog':'passed','mobile_overflow':False}))
    browser.close()
