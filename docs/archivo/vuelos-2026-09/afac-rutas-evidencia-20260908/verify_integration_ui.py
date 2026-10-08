"""Offline browser checks for the locally generated, owned dashboard."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]
OUTPUT=Path(__file__).parent
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page()
    errors=[];remote=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:remote.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.goto((ROOT/'prototypes/etapa-11/resumen_ejecutivo.html').as_uri())
    page.locator('#tab-flights').click()
    page.wait_for_function("document.querySelectorAll('#panel-flights .route-summary-row').length > 0")
    page.wait_for_timeout(700)
    results=[]
    for width in (1440,736,360):
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_timeout(700)
        overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not overflow, f'Horizontal overflow {width}'
        results.append({'width':width,'horizontal_overflow':overflow})
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#panel-flights #airport-search-toggle').click()
    page.locator('#panel-flights #airport-search-input').fill('LHR')
    page.wait_for_timeout(300)
    # The existing search implementation exposes buttons in the result list.
    page.locator('#panel-flights #airport-search-results button').first.click()
    page.wait_for_timeout(400)
    panel=page.locator('#panel-flights #airport-tooltip')
    assert 'LHR' in panel.inner_text() and 'CAA' in panel.inner_text()
    assert 'N/D' in panel.inner_text()
    panel.locator('.route-expand-toggle').first.click()
    assert panel.locator('.route-direction-detail').first.is_visible()
    page.locator('#panel-flights #map-panel').screenshot(path=str(OUTPUT/'international-routes-desktop.png'))
    assert not errors, errors
    assert not remote, remote
    (OUTPUT/'integration-ui.json').write_text(json.dumps({'viewports':results,'errors':errors,'remote_requests':remote,'lhr_source_visible':True,'direction_toggle':True},indent=2),encoding='utf-8')
    browser.close()
