"""Focused initial manifest checks against running frontend; all API calls intercepted."""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

out = Path(__file__).parent
rows = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='msedge')
    for label, status, assignments in [
        ('nonempty', 200, [dict(mission_id='INDEPENDENT-MISSION', airframe_id='INDEPENDENT-AIRCRAFT',
                              crew_id='INDEPENDENT-CREW', corridor_id='INDEPENDENT-CORRIDOR', slot=2)]),
        ('empty', 200, []), ('unavailable', 503, [])
    ]:
        context = browser.new_context(viewport={'width':1440, 'height':1000})
        context.add_init_script("localStorage.setItem('air-power-data-mode','live')")
        calls = []
        errors = []
        def intercept(route):
            path = urlparse(route.request.url).path.removeprefix('/api/v1')
            calls.append(path)
            headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}
            if route.request.method == 'OPTIONS':
                route.fulfill(status=204, headers=headers)
                return
            code = status if path == '/plans/active' else 200
            data = []
            if path == '/health': data = {'status':'ok','service':'probe'}
            if path == '/forecasts/FORECAST-01': data = dict(id='FORECAST-01',target='Demand',points=[],coverage=88,highUncertainty=False)
            if path == '/plans/active': data = dict(status='optimal',revision=2,assignments=assignments,served_priority=5)
            route.fulfill(status=code, headers=headers, content_type='application/json', body=json.dumps(data))
        context.route('**/api/v1/**', intercept)
        page = context.new_page()
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto('http://localhost:3000/', wait_until='networkidle')
        # Give hydration and the initial effect an explicit additional opportunity to complete.
        page.wait_for_timeout(5000)
        board = page.locator('.resource-boards-container')
        text = board.inner_text()
        ok = ('INDEPENDENT-MISSION' in text and 'INDEPENDENT-AIRCRAFT' in text) if label == 'nonempty' else 'VERIFIED OPTIMAL' not in text
        page.screenshot(path=str(out / f'cold-start-{label}.png'), full_page=True)
        rows.append(dict(id=f'BROWSER-PROBE-{len(rows)+1}', scenario=label, status='PASS' if ok else 'FAIL',
                         active_plan_request_count=calls.count('/plans/active'), calls=calls, page_errors=errors,
                         shows_returned_mission='INDEPENDENT-MISSION' in text,
                         shows_verified_optimal='VERIFIED OPTIMAL' in text, manifest_excerpt=text[:2000]))
        if label == 'nonempty':
            fixture_missions = [x for x in ('MSN-OP-901', 'MSN-OP-902', 'MSN-LOG-110') if x in text]
            invented_facts = [x for x in ('8,500 kg', '8h left / 10h max', 'Base-Alpha', 'Safety Margin: +45 min') if x in text]
            rows.append(dict(id=f'BROWSER-PROBE-{len(rows)+1}', scenario='nonempty-evidence-integrity',
                             status='PASS' if not fixture_missions and not invented_facts else 'FAIL',
                             expected='live manifest contains only returned assignments and no unsupported operational facts',
                             actual=dict(extra_fixture_missions=fixture_missions, unsupported_facts=invented_facts,
                                         returned_assignments=assignments)))
        context.close()
    browser.close()
(out / 'browser-probes.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
print(json.dumps(rows, indent=2))
raise SystemExit(int(any(r['status'] == 'FAIL' for r in rows)))
