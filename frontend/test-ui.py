from playwright.sync_api import sync_playwright
from pathlib import Path
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width":1440,"height":1100}, device_scale_factor=1)
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://localhost:3000/overview')
    page.wait_for_load_state('networkidle')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/overview.png',full_page=True)
    print('Overview loaded')
    for route in ['data-sources','evidence','decision-validity','predictions','planning','replanning','digital-twin','verification','benchmarks']:
        response=page.goto('http://localhost:3000/'+route)
        page.wait_for_load_state('networkidle')
        assert response.status==200,route
        assert page.get_by_role('heading',level=1).count()==1,route
    page.goto('http://localhost:3000/planning')
    page.get_by_role('button',name='Run optimisation').click()
    page.get_by_role('link',name='Verify & review').click()
    page.get_by_role('button',name='Run independent checks').click()
    page.get_by_label('Reviewer',exact=True).fill('QA Analyst')
    page.get_by_label('Review reason').fill('All independent checks passed.')
    page.get_by_role('button',name='Approve result').click()
    assert page.get_by_text('Review recorded: Approved.').is_visible()
    page.goto('http://localhost:3000/replanning')
    page.get_by_label('Updated capacity',exact=True).fill('1')
    page.get_by_role('button',name='Apply input change').click()
    page.goto('http://localhost:3000/verification')
    assert page.get_by_role('button',name='Approve result').is_disabled()
    page.get_by_role('button',name='Run independent checks').click()
    assert page.get_by_text('Invalidated',exact=True).is_visible()
    page.goto('http://localhost:3000/digital-twin')
    page.get_by_role('button',name='Run experiment').click()
    assert page.get_by_role('button',name='Export experiment').is_visible()
    page.goto('http://localhost:3000/data-sources')
    before=page.locator('tbody tr').count()
    page.get_by_role('button',name='Replay event').click()
    assert page.locator('tbody tr').count()==before+1
    page.get_by_role('button',name='Inspect v1').first.click()
    assert page.get_by_role('dialog').is_visible()
    page.get_by_role('button',name='Close record details').click()
    page.set_viewport_size({'width':390,'height':844})
    page.goto('http://localhost:3000/overview')
    page.wait_for_load_state('networkidle')
    page.screenshot(path='test-results/mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    page.get_by_role('button',name='Toggle navigation').click()
    assert page.get_by_role('link',name='Digital Twin Lab LAB').is_visible()
    print('All 10 routes, planning approval guard, invalidation, experiment, replay, drawer, and mobile checks passed.')
    print('Browser errors:',errors)
    assert not errors
    browser.close()

