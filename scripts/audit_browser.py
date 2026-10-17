"""Real-browser scenarios against the running frontend, with isolated API fixtures."""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect


def main(args):
    rows=[]
    output=Path(args.output)
    screenshots=output.parent/"screenshots"
    screenshots.mkdir(parents=True,exist_ok=True)

    def case(category,name,inputs,expected,run,issue=""):
        start=time.perf_counter()
        try:
            ok,actual=run()
            status="PASS" if ok else "FAIL"
        except Exception as e:
            status,actual="FAIL",{"exception":type(e).__name__,"message":str(e)[:1500]}
        rows.append(dict(id=f"BROWSER-{len(rows)+1:03d}",category=category,name=name,layer="real-browser+intercepted-api",
                         inputs=inputs,expected=expected,actual=actual,status=status,issue=issue if status=="FAIL" else "",
                         duration_ms=round((time.perf_counter()-start)*1000,3)))
        output.write_text(json.dumps(rows,indent=2),encoding="utf-8")

    schedule=dict(id="AUDIT-SCHEDULE",version=1,assignments=[dict(taskId="TSK-101",resourceId="AUDIT-AIRCRAFT",crewId="AUDIT-CREW",corridorId="AUDIT-CORRIDOR",start=3,end=5)],objectives=dict(utilization=75,cost=200,balance=80),verification="verified")
    decision=dict(id="DEC-1",type="Transport",version=2,status="stale",createdAt="2026-10-16",assumptions=[],dependencies=[])
    approval=dict(id="APP-1",targetId=schedule["id"],type="Schedule",status="pending",verification="verified",submittedBy="Audit",submittedAt="2026-10-16",summary="Test transport review")
    endpoints={
        "/health":dict(status="ok",service="audit-fixture"),
        "/validity/decisions":[decision],"/validity/decisions/DEC-1":decision,
        "/ingestion/status":[dict(topic="transport",status="active",rate="20/s",lag=0,errorCount=0)],
        "/ingestion/flagged":[dict(id="REC-1",source="Audit",time="2026-10-16",reason="Old sample",status="Stale",version=1,duplicate=False)],
        "/evidence/issues":[dict(id="REC-1",issueClass="stale",status="open",sourceId="AUDIT",detectedAt="2026-10-16",affectedResource="A1")],
        "/evidence/issues/REC-1/autopsy":dict(issueId="REC-1",issueClass="stale",claims=[],provenance=[],missingInformation=[],uncertainty=[]),
        "/forecasts/FORECAST-01":dict(id="FORECAST-01",target="Transport demand",points=[dict(t="00",mean=5,lower=3,upper=7)],coverage=88,highUncertainty=True),
        "/planning/alternatives":[schedule],"/planning/solve":schedule,"/planning/schedules/AUDIT-SCHEDULE":schedule,
        "/approvals":[approval],"/verification/check":dict(outcome="verified",violations=[],uncertainty_flags=[]),
        "/stress/runs":[],"/agents/requests":[],"/audit":[],"/benchmarks/results":[],"/benchmarks/ablations":[],
        "/replanning/diff/AUDIT-SCHEDULE/AUDIT-SCHEDULE":dict(added=[],removed=[],moved=[],unchanged=1),
    }
    paths=["/","/ingestion","/evidence","/evidence/REC-1","/validity","/validity/DEC-1","/forecasts","/planning","/planning/compare","/stress-lab","/explanations","/approvals","/audit","/benchmarks"]
    with sync_playwright() as p:
        try:browser=p.chromium.launch(headless=True,channel="msedge")
        except Exception:browser=p.chromium.launch(headless=True)
        context=browser.new_context()
        state={"failure":None,"disruption_status":200,"assignments":[],"calls":[]}
        def intercept(route):
            path=urlparse(route.request.url).path.removeprefix("/api/v1")
            state["calls"].append(dict(method=route.request.method,path=path))
            if route.request.method=="OPTIONS":
                route.fulfill(status=204,headers={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"*","Access-Control-Allow-Methods":"*"});return
            if state["failure"]=="network":route.abort("failed");return
            status=state["failure"] if isinstance(state["failure"],int) else 200
            if path=="/disruption":
                status=state["disruption_status"]
                data=dict(status="replanned",revision=9,assignments=state["assignments"],served_priority=0)
            elif path=="/plans/active":data=dict(status="optimal",revision=9,assignments=state["assignments"],served_priority=0)
            else:data=endpoints.get(path,[])
            if status!=200:data=dict(code="audit_failure",message="Injected test failure")
            route.fulfill(status=status,content_type="application/json",body=json.dumps(data),headers={"Access-Control-Allow-Origin":"*"})
        context.route("**/api/v1/**",intercept)
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.set_default_timeout(4500)
        context.add_init_script("localStorage.setItem('air-power-data-mode','live')")
        for width,height in [(1440,1000),(390,844)]:
            page.set_viewport_size(dict(width=width,height=height))
            for path in paths:
                def run(path=path):
                    errors.clear();state["failure"]=None
                    response=page.goto(args.base+path,wait_until="networkidle")
                    heading=page.locator("h1").count()>0
                    overflow=page.evaluate("document.documentElement.scrollWidth > innerWidth")
                    return response.status==200 and heading and not errors and not overflow,dict(http=response.status,heading=heading,overflow=overflow,pageerrors=list(errors))
                case("browser-routes","route renders with bounded layout",dict(path=path,width=width),"HTTP 200, visible heading, no page exception or horizontal overflow",run,"UI-LAYOUT")
        page.set_viewport_size(dict(width=1440,height=1000))
        for status,path in __import__('itertools').product(["network",403,404,429,503],["/ingestion","/evidence","/validity","/forecasts","/planning","/approvals"]):
            def run(status=status,path=path):
                state["failure"]=status
                page.goto(args.base+path,wait_until="networkidle")
                expect(page.locator(".request-failure").first).to_be_visible()
                return True,dict(failure_text=page.locator(".request-failure").first.inner_text()[:600])
            case("browser-failure-states","API failure is visible",dict(path=path,status=status),"explicit request failure rather than fabricated successful data",run,"UI-FAILURE")
        state["failure"]=None
        def planning_evidence():
            page.goto(args.base+"/planning",wait_until="networkidle")
            page.get_by_role("button",name="Run Optimisation",exact=True).click()
            manifest=page.locator("table").filter(has_text="Aircraft & Base")
            expect(manifest).to_be_visible()
            text=manifest.inner_text()
            manifest.screenshot(path=str(screenshots/"planning-evidence.png"))
            return all(s in text for s in ("AUDIT-AIRCRAFT","AUDIT-CREW","AUDIT-CORRIDOR","3:00","5:00")),dict(manifest=text)
        case("browser-evidence-integrity","planning respects returned IDs and times",schedule,"display exact returned aircraft, crew, corridor and interval",planning_evidence,"UI-API-METADATA")
        for scenario,status in __import__('itertools').product(["storm_front","mechanical_fault","threat_spike"],[200,403,503]):
            def run(scenario=scenario,status=status):
                state["disruption_status"]=status;state["assignments"]=[]
                page.goto(args.base+"/",wait_until="networkidle")
                state["calls"].clear()
                names={"storm_front":"Storm Front in Corridor Charlie","mechanical_fault":"Hydraulic Failure on Airframe","threat_spike":"Hostile SAM Radar Spike"}
                # Discover control text before selecting the scenario; absent controls are recorded explicitly.
                buttons=page.locator('.magi-disruption-bar').get_by_role("button").all_text_contents()
                match=next((label for label in buttons if names[scenario].lower() in label.lower()),None)
                if match is None:return False,dict(missing_control=names[scenario],buttons=buttons)
                page.get_by_role("button",name=match.strip(),exact=True).click()
                page.wait_for_timeout(2600)
                body=page.locator(".resource-boards-container").inner_text()
                calls=[c for c in state["calls"] if c["path"]=="/disruption"]
                verified="VERIFIED OPTIMAL" in body
                if scenario=="storm_front" and status==503:page.screenshot(path=str(screenshots/"failed-disruption-manifest.png"),full_page=True)
                return bool(calls) and not verified,dict(disruption_requests=calls,shows_verified_optimal=verified,response_status=status,manifest_excerpt=body[:1500])
            case("browser-evidence-integrity","empty/failed disruption cannot certify fixture sorties",dict(scenario=scenario,status=status,assignments=[]),
                 "request reaches API; no successful/optimal claim when response fails or contains no assignments",run,"UI-FALSE-CERTIFICATION")
        def cold_start():
            state["disruption_status"]=200
            state["assignments"]=[dict(mission_id="AUDIT-NEW-MISSION",airframe_id="AUDIT-NEW-AIRCRAFT",crew_id="AUDIT-NEW-CREW",corridor_id="AUDIT-ROUTE",slot=1)]
            page.goto(args.base+"/",wait_until="networkidle")
            text=page.locator(".resource-boards-container").inner_text()
            return "AUDIT-NEW-MISSION" in text and "AUDIT-NEW-AIRCRAFT" in text,dict(returned=state["assignments"],manifest_excerpt=text[:1600])
        case("browser-evidence-integrity","initial live manifest renders new backend mission",{},"new backend mission visible without requiring fixture ID match or scenario click",cold_start,"UI-FIXTURE-ID-DEPENDENCY")
        context.close();browser.close()
    print(json.dumps({"browser_cases":len(rows),"pass":sum(r['status']=='PASS' for r in rows),"fail":sum(r['status']=='FAIL' for r in rows)}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base",default="http://localhost:3000")
    parser.add_argument("--output",required=True)
    main(parser.parse_args())
