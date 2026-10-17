"""Repeatable behavioral audit; writes evidence and never repairs application code.

Run from the repository root: python scripts/audit_system.py --help
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import inspect
import itertools
import json
import math
import platform
import re
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/agent_engine/src"))

import httpx
from api import domain_routes as domain, routes, server
from negotiation.coordinator import MagiCoordinator
from solver.model import Airframe, Assignment, Corridor, Crew, Mission, SolverResult
from solver.optimizer import AirOperationsOptimizer
from solver.verifier import IndependentVerifier
from transport.equilibrium import EquilibriumEngine


class MemoryStorage:
    """Explicit test double: exercises application orchestration, not PostgreSQL."""
    def __init__(self, fail=None):
        self.plans, self.transcripts, self.fail = [], [], fail

    async def save_plan(self, value):
        if self.fail == "plan":
            raise OSError("Injected test storage failure")
        self.plans.append(copy.deepcopy(value))
        return SimpleNamespace(id=f"audit-plan-{len(self.plans)}")

    async def record_transcripts(self, items):
        if self.fail == "transcript":
            raise OSError("Injected test transcript failure")
        self.transcripts.extend(copy.deepcopy(items))

    async def close(self):
        pass


def world(minutes=60, capacity=1000, duty=12, deadline=4, count=1):
    return (
        [Mission(f"M{i}", "HUB", "CLINIC", 1000, priority=5+i, deadline_slot=deadline) for i in range(count)],
        [Airframe(f"A{i}", capacity, 2000) for i in range(count)],
        [Crew(f"C{i}", duty_hours_left=duty) for i in range(count)],
        [Corridor(f"R{i}", "HUB", "CLINIC", 500, minutes) for i in range(count)],
    )


def engine_for(w=None, storage=None):
    m, a, c, r = w or world()
    e = EquilibriumEngine(storage=storage or MemoryStorage(), debounce_seconds=0.025)
    e.initialize_world(a, c, r, m, run_id="isolated-audit")
    e.establish_initial_equilibrium()
    return e


async def cancel_engine(e):
    if e._replan_task and not e._replan_task.done():
        e._replan_task.cancel()
        await asyncio.gather(e._replan_task, return_exceptions=True)


REGISTRIES = ["SCHEDULES", "APPROVALS", "DECISIONS", "AUDIT_LOG", "STRESS_RUNS", "AGENT_REQUESTS"]
ORIGINAL = {key: copy.deepcopy(getattr(domain, key)) for key in REGISTRIES}


def reset_api():
    for key, value in ORIGINAL.items():
        setattr(domain, key, copy.deepcopy(value))
    a, c, r, m = server.create_demo_world()
    e = engine_for((m, a, c, r))
    routes.set_engine(e)
    return e


def fingerprints():
    result = {}
    for folder in ("services/agent_engine/src", "services/simulator", "frontend/src"):
        for p in sorted((ROOT / folder).rglob("*")):
            if p.suffix in (".py", ".tsx", ".ts", ".js", ".css") and "__pycache__" not in p.parts:
                result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


class Ledger:
    def __init__(self, output):
        self.output, self.rows = output, []
        self.started = datetime.now(timezone.utc).isoformat()
        self.covered_operations = set()

    async def case(self, category, name, inputs, expected, fn, *, layer="direct-domain", issue=""):
        start = time.perf_counter()
        try:
            answer = fn()
            if inspect.isawaitable(answer):
                answer = await answer
            ok, actual = answer
            status = "PASS" if ok else "FAIL"
        except Exception as exc:
            status, actual = "FAIL", {"exception": type(exc).__name__, "message": str(exc)[:1000],
                                       "traceback": traceback.format_exc(limit=4)}
        self.rows.append(dict(id=f"AUD-{len(self.rows)+1:04d}", category=category, name=name, layer=layer,
                              inputs=inputs, expected=expected, actual=actual, status=status,
                              issue=issue if status == "FAIL" else "", duration_ms=round((time.perf_counter()-start)*1000, 3)))
        if len(self.rows) % 100 == 0:
            print(json.dumps({"completed": len(self.rows), "status": dict(Counter(r["status"] for r in self.rows))}), flush=True)

    def save(self, metadata):
        self.output.mkdir(parents=True, exist_ok=True)
        totals = dict(Counter(r["status"] for r in self.rows))
        groups = {g: dict(Counter(r["status"] for r in self.rows if r["category"] == g)) for g in sorted({r["category"] for r in self.rows})}
        summary = {"started_utc": self.started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                   "total": len(self.rows), "totals": totals, "by_category": groups, **metadata}
        (self.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (self.output / "cases.json").write_text(json.dumps(self.rows, indent=2, default=str), encoding="utf-8")
        with (self.output / "cases.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0]) if self.rows else ["id"])
            writer.writeheader()
            for row in self.rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v for k, v in row.items()})
        (self.output / "api-coverage.json").write_text(json.dumps(sorted(self.covered_operations), indent=2), encoding="utf-8")
        print(json.dumps({"output": str(self.output), "total": len(self.rows), "totals": totals, "groups": groups}), flush=True)
        return summary


def result(ok, **actual):
    return bool(ok), actual


async def solver_cases(log):
    # Independent oracle uses real duration in hours; it never calls the verifier/candidate generator.
    for minutes, deadline, capacity, offset in itertools.product(
        [1, 59, 60, 61, 119, 120, 121, 179, 180, 181, 239, 240, 241, 300],
        range(6), [999, 1000, 1001], [-0.01, 0, 0.01]
    ):
        duty = minutes/60 + offset
        w = world(minutes, capacity, duty, deadline)
        should_serve = capacity >= 1000 and duty >= minutes/60 and math.ceil(minutes/60) <= deadline
        def run(w=w, should_serve=should_serve, minutes=minutes):
            solved = AirOperationsOptimizer().solve(*w)
            arrivals = all(a.estimated_arrival_slot == a.slot + math.ceil(minutes/60) for a in solved.assignments)
            return result(bool(solved.assignments) == should_serve and arrivals and solved.status == "optimal",
                          status=solved.status, served=len(solved.assignments), assignments=[asdict(a) for a in solved.assignments])
        await log.case("solver-boundaries", "capacity/duty/duration/deadline boundary", dict(minutes=minutes, deadline=deadline, capacity=capacity, duty=duty),
                       f"served={should_serve}; arrival=departure+ceil(minutes/60); optimal status", run, issue="SOLVER-BOUNDARY")
    await resource_cases(log)


async def resource_cases(log):
    for n, available_a, available_c in itertools.product(range(1, 5), range(4), range(4)):
        w = world(count=n)
        m, a, c, r = w
        # Preserve surplus resources as distinct scenarios instead of slicing
        # an n-resource list, which would repeat the same world when available > n.
        a = [Airframe(f"A{i}",1000,2000) for i in range(available_a)]
        c = [Crew(f"C{i}") for i in range(available_c)]
        def run(m=m, a=a, c=c, r=r):
            solved = AirOperationsOptimizer().solve(m, a, c, r)
            count = min(len(m), len(a), len(c))
            expected_priority = sum(sorted((x.priority for x in m), reverse=True)[:count])
            return result(len(solved.assignments) == count and solved.served_priority == expected_priority,
                          served=len(solved.assignments), priority=solved.served_priority, expected_priority=expected_priority)
        await log.case("solver-resource-contention", "scarcity preserves highest priority", dict(missions=n, aircraft=len(a), crews=len(c)),
                       "serve min(missions, aircraft, crews), maximizing served priority", run, issue="SOLVER-CONTENTION")


async def verifier_cases(log):
    changes = ["baseline", "missing_mission", "missing_aircraft", "missing_crew", "missing_corridor", "unknown_mission", "unknown_aircraft", "unknown_crew", "unknown_corridor",
               "negative_slot", "fractional_slot", "boolean_slot", "string_slot", "late_departure", "aircraft_unavailable", "crew_unavailable", "overweight", "range_exceeded",
               "unqualified", "exhausted", "storm", "wrong_route", "duplicate_mission", "forged_arrival", "crew_alias", "corridor_alias", "slot_beyond_horizon"]
    for minutes, change in itertools.product([1, 59, 60, 61, 120, 121], changes):
        def run(minutes=minutes, change=change):
            m, a, c, r = world(minutes=minutes, count=2)
            assignments = [dict(mission_id="M0", airframe_id="A0", crew_id="C0", corridor_id="R0", slot=0, estimated_arrival_slot=math.ceil(minutes/60))]
            one = assignments[0]
            if change.startswith("missing_"): one.pop({"mission":"mission_id", "aircraft":"airframe_id", "crew":"crew_id", "corridor":"corridor_id"}[change[8:]])
            elif change.startswith("unknown_"): one[{"mission":"mission_id", "aircraft":"airframe_id", "crew":"crew_id", "corridor":"corridor_id"}[change[8:]]] = "DOES-NOT-EXIST"
            elif change == "negative_slot": one["slot"] = -1
            elif change == "fractional_slot": one["slot"] = 0.5
            elif change == "boolean_slot": one["slot"] = True
            elif change == "string_slot": one["slot"] = "oops"
            elif change == "late_departure": one["slot"] = 4
            elif change == "aircraft_unavailable": a[0] = replace(a[0], status="maintenance")
            elif change == "crew_unavailable": c[0] = replace(c[0], status="rest")
            elif change == "overweight": a[0] = replace(a[0], capacity_kg=999)
            elif change == "range_exceeded": a[0] = replace(a[0], max_range_km=499)
            elif change == "unqualified": c[0] = replace(c[0], qualifications=("other",))
            elif change == "exhausted": c[0] = replace(c[0], duty_hours_left=0)
            elif change == "storm": r[0] = replace(r[0], weather_condition="storm")
            elif change == "wrong_route": r[0] = replace(r[0], to_base="UNRELATED")
            elif change == "duplicate_mission": assignments.append(dict(mission_id="M0", airframe_id="A1", crew_id="C1", corridor_id="R1", slot=1))
            elif change == "forged_arrival": one["estimated_arrival_slot"] = -1
            elif change == "crew_alias": one["crewId"] = one.pop("crew_id")
            elif change == "corridor_alias": one["corridorId"] = one.pop("corridor_id")
            elif change == "slot_beyond_horizon": one["slot"] = 2
            horizon = 1 if change == "slot_beyond_horizon" else 8
            try:
                checked = IndependentVerifier.verify_complete_schedule(assignments, m, a, c, r, horizon=horizon)
            except Exception as e:
                return result(False, exception=type(e).__name__, message=str(e), assignments=assignments)
            # Aliases produced by the actual solve API should be supported consistently.
            expected = "verified" if change in ("baseline", "crew_alias", "corridor_alias") else "invalid"
            return result(checked["outcome"] == expected, expected_outcome=expected, **checked)
        await log.case("independent-verifier", change, dict(minutes=minutes, mutation=change),
                       "valid baseline/API aliases pass; malformed, forged or infeasible assignment returns structured invalid", run, issue=f"VERIFIER-{change.upper()}")


async def telemetry_cases(log):
    changes = ["maintenance", "recovery", "capacity_drop", "capacity_zero", "duty_zero", "duty_drop", "range_zero", "range_drop", "qualifications_removed", "weather_storm", "weather_recovery", "airport_closed", "cargo_mass", "stale_sequence", "expired_event"]
    for minutes, change in itertools.product([30, 60, 90, 120], changes):
        async def run(minutes=minutes, change=change):
            w = world(minutes=minutes)
            if change in ("recovery", "weather_recovery"):
                m, a, c, r = w
                if change == "recovery": a[0] = replace(a[0], status="maintenance")
                else: r[0] = replace(r[0], weather_condition="storm")
            e = engine_for(w)
            event = dict(type="aircraft.status", entityId="A0", sequence=2, data={"status":"available"})
            expected = True
            if change == "maintenance": event["data"]["status"] = "maintenance"
            elif change == "capacity_drop": event["data"]["capacityKg"] = 999
            elif change == "capacity_zero": event["data"]["capacityKg"] = 0
            elif change == "range_zero": event["data"]["maxRangeKm"] = 0
            elif change == "range_drop": event["data"]["maxRangeKm"] = 499
            elif change in ("duty_zero", "duty_drop", "qualifications_removed"):
                event.update(type="crew.availability", entityId="C0", data={"status":"available"})
                if change == "qualifications_removed": event["data"]["qualifications"] = ["other"]
                else: event["data"]["dutyHoursLeft"] = 0 if change == "duty_zero" else minutes/60-0.01
            elif change in ("weather_storm", "weather_recovery"):
                event.update(type="weather.observation", entityId="CLINIC", data={"condition":"storm" if change == "weather_storm" else "clear"})
            elif change == "airport_closed": event.update(type="airport.capacity", entityId="CLINIC", data={"status":"closed", "arrivalsPerHour":0, "departuresPerHour":0})
            elif change == "cargo_mass": event.update(type="cargo.request", entityId="M0", data={"massKg":1001})
            elif change == "stale_sequence":
                await e.ingest_event({**event, "sequence":10, "data":{"status":"maintenance"}})
                event["sequence"] = 1
                expected = False
            elif change == "expired_event":
                event.update(observedAt="2000-01-01T00:00:00Z", validUntil="2000-01-02T00:00:00Z", data={"status":"maintenance"})
                expected = False
            broken = await e.ingest_event(event)
            await cancel_engine(e)
            await e.trigger_replan()
            served = len(e.active_assignments)
            if change in ("recovery", "weather_recovery", "expired_event"): expected_served = 1
            else: expected_served = 0
            ok = broken == expected and served == expected_served
            return result(ok, broken=broken, expected_broken=expected, served=served, expected_served=expected_served,
                          aircraft=asdict(e.airframes["A0"]), crew=asdict(e.crews["C0"]))
        await log.case("telemetry-transitions", change, dict(minutes=minutes, transition=change),
                       "apply fresh observations, preserve zero, reject old/expired input, replan on feasibility/recovery changes", run, layer="isolated-engine+memory-storage", issue=f"TELEMETRY-{change.upper()}")


async def api_cases(log):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app, raise_app_exceptions=False), base_url="http://isolated-audit") as client:
        async def request(method, path, body=None, headers=None):
            for template, methods in getattr(log, "live_schema", {}).get("paths", {}).items():
                pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
                if method.lower() in methods and re.fullmatch(pattern, path):
                    log.covered_operations.add(method + " " + template)
            response = await client.request(method, path, json=body, headers=headers)
            try: payload = response.json()
            except ValueError: payload = response.text[:1000]
            return response.status_code, payload

        for capacity, horizon in itertools.product([-2, 0, 1, 2, 3, 4, 8, 16], [-1, 0, 1, 2, 3, 4, 8]):
            async def run(capacity=capacity, horizon=horizon):
                reset_api()
                status, payload = await request("POST", "/api/v1/planning/solve", dict(capacity=capacity, horizon=horizon))
                valid = capacity > 0 and horizon > 0
                # With one resource, the first 75-minute mission needs two hour slots.
                can_serve = valid and (horizon >= 2 or capacity >= 2)
                expected = "verified" if can_serve else "invalid"
                checks = status == 200 and payload.get("verification") == expected
                checks = checks and all(0 <= a["start"] < a["end"] <= horizon for a in payload.get("assignments", []))
                return result(checks, http=status, expected_verification=expected, response=payload)
            await log.case("api-solve-boundaries", "solve domain bounds and feasibility", dict(capacity=capacity, horizon=horizon),
                           "invalid bounds fail closed; feasible requests produce verifiable assignments within horizon", run, layer="ASGI+real-solver", issue="API-SOLVE")

        invalid_values = [None, "bad", [], {}, True, 1.5, "4", "", [1], {"x":1}]
        for field, value in itertools.product(["capacity", "horizon"], invalid_values):
            async def run(field=field, value=value):
                reset_api()
                status, payload = await request("POST", "/api/v1/planning/solve", {"capacity":2,"horizon":4,field:value})
                return result(status == 422, http=status, response=payload)
            await log.case("api-input-validation", "strict integer solve parameter", {field:value}, "HTTP 422 for non-integer JSON type; booleans and coercible strings are not integers", run, layer="ASGI", issue="API-COERCION")

        malformed = [None, [], 5, True, "text", {"unexpected":1}]
        endpoints = ["/planning/solve", "/verification/check", "/stress/runs", "/agents/requests", "/approvals/APP-101/decision", "/validity/reverify", "/events", "/disruption"]
        for path, body in itertools.product(endpoints, malformed):
            if path == "/verification/check" and body is None: continue
            async def run(path=path, body=body):
                e=reset_api()
                status, payload = await request("POST", "/api/v1"+path, body)
                await cancel_engine(e)
                return result(status in (400,422), http=status, response=payload)
            await log.case("api-input-validation", "malformed request envelope", {"path":path,"body":body},
                           "reject structurally invalid or unknown-field request with 400/422; no 500 or silent acceptance", run, layer="ASGI", issue="API-ENVELOPE")

        for capacity, horizon in itertools.product([2,3,4], [2,3,4,8]):
            async def run(capacity=capacity, horizon=horizon):
                reset_api()
                _, solved = await request("POST", "/api/v1/planning/solve", dict(capacity=capacity,horizon=horizon))
                status, checked = await request("POST", "/api/v1/verification/check", dict(target_id=solved["id"],capacity=capacity,horizon=horizon))
                return result(status == 200 and solved["verification"] == checked["outcome"] == "verified", solved=solved, checked=checked)
            await log.case("api-solve-verify-roundtrip", "verify the exact schedule just generated", dict(capacity=capacity,horizon=horizon),
                           "solver and verification endpoint agree using the same resource registry and schema", run, layer="ASGI+real-solver", issue="API-REGISTRY-DRIFT")

        for decision in ["approve", "approved", "reject", "rejected", "anything", "", "pending", "VERIFIED"]:
            async def run(decision=decision):
                reset_api()
                domain.APPROVALS[0]["verification"] = "invalid"
                status, payload = await request("POST", "/api/v1/approvals/APP-101/decision", dict(decision=decision,reviewer="Audit",rationale="Test invalid schedule gate"))
                return result(status in (400,401,403,409,422), http=status,response=payload)
            await log.case("api-approval-gates", "invalid schedule cannot receive arbitrary approval status", {"decision":decision},
                           "server rejects invalid target/status irrespective of frontend button state", run, layer="ASGI", issue="APPROVAL-GATE")

        for path, body in [("/replan",{}),("/events",{"scenario":"mechanical_fault"}),("/disruption",{"scenario":"storm_front"}),
                           ("/planning/solve",{"capacity":2,"horizon":4}),("/validity/reverify",{"id":"DEC-803"}),
                           ("/stress/runs",{"scenario":"clean","faultSeverity":"low","seed":42}),
                           ("/agents/requests",{"query":"Explain current evidence"}),
                           ("/approvals/APP-101/decision",{"decision":"approved","reviewer":"Audit","rationale":"Test permission gate"})]:
            async def run(path=path,body=body):
                e=reset_api()
                status,payload=await request("POST","/api/v1"+path,body)
                await cancel_engine(e)
                return result(status in (401,403),http=status,response=payload)
            await log.case("api-authorization", "unauthenticated mutation denied", {"path":path,"body":body},
                           "401/403; source/admin/operator identity required for mutations",run,layer="ASGI",issue="AUTH-MISSING")

        for scenario in ["storm_front","mechanical_fault","crew_fatigue","reset"]:
            async def run(scenario=scenario):
                e=reset_api()
                _, first=await request("POST","/api/v1/disruption",{"scenario":scenario})
                revision=e.revision
                await asyncio.sleep(0.09)
                extra=e.revision-revision
                await cancel_engine(e)
                return result(extra == 0,response=first,revision_after_response=revision,revision_after_debounce=e.revision)
            await log.case("api-disruption-debounce", "one command causes one plan revision", {"scenario":scenario},
                           "no second automatic replan after HTTP handler already replanned",run,layer="ASGI+memory-storage",issue="DOUBLE-REPLAN")

        for failure in ("timeout","infeasible"):
            async def run(failure=failure):
                reset_api()
                with patch.object(domain.optimizer,"solve",return_value=SolverResult(failure,0,0)):
                    status,payload=await request("POST","/api/v1/planning/solve",{"capacity":2,"horizon":4})
                return result(status==200 and payload["verification"]=="invalid" and not payload["assignments"],http=status,response=payload)
            await log.case("fault-injection", "solver failure cannot fabricate assignments", {"solver_status":failure},
                           "invalid result with no fabricated assignments",run,layer="ASGI+injected-solver-status",issue="FABRICATED-FALLBACK")


async def fault_cases(log):
    for failure in ("plan","transcript"):
        async def run(failure=failure):
            store=MemoryStorage(failure)
            e=engine_for(storage=store)
            try: await e.trigger_replan()
            except Exception: pass
            return result(not e.is_equilibrium, equilibrium=e.is_equilibrium,plans_written=len(store.plans),transcripts_written=len(store.transcripts))
        await log.case("fault-injection", "storage failure must not claim durable equilibrium", {"failure":failure},
                       "unavailable/degraded equilibrium when audit commit fails",run,layer="injected-storage-failure",issue="PERSISTENCE-FAIL-OPEN")
    for count in [1,2,3,4]:
        def run(count=count):
            w=world(count=count)
            out=MagiCoordinator().negotiate_and_solve(*w)
            seeds=out["candidate_seeds"]
            check=IndependentVerifier.verify_complete_schedule(seeds,*w)
            return result(check["outcome"]=="verified" and len(seeds)==count,seeds=seeds,verification=check)
        await log.case("negotiation", "consensus seed is globally feasible and complete", {"missions":count},
                       "all feasible independent requests receive conflict-free seed assignments",run,issue="NEGOTIATION-SEED")
    for deadline in [0,1,2]:
        def run(deadline=deadline):
            w=world(minutes=121,deadline=deadline)
            out=MagiCoordinator().negotiate_and_solve(*w)
            return result(not out["candidate_seeds"],seeds=out["candidate_seeds"],solver_assignments=[asdict(a) for a in out["solver_result"].assignments])
        await log.case("negotiation", "agents must not announce consensus on late arrival", {"minutes":121,"deadline":deadline},
                       "no accepted seed when flight cannot arrive by deadline",run,issue="NEGOTIATION-DEADLINE")
    for prior_slot in [0,1,2,3]:
        def run(prior_slot=prior_slot):
            w=world()
            prior=[dict(mission_id="M0",airframe_id="A0",crew_id="C0",corridor_id="R0",slot=prior_slot)]
            solved=AirOperationsOptimizer().solve(*w,prior_assignments=prior)
            return result(solved.assignments[0].slot==prior_slot,prior=prior,assignments=[asdict(a) for a in solved.assignments])
        await log.case("solver-stability", "unchanged feasible schedule retains slot", {"prior_slot":prior_slot},
                       "churn penalty preserves existing slot within this objective's delay trade-off",run,issue="CHURN")
    for missing in ("crew_id","corridor_id","mission_id"):
        def run(missing=missing):
            e=engine_for()
            a=copy.deepcopy(e.active_assignments[0]);a.pop(missing)
            e.apply_restored_plan(SimpleNamespace(run_id="old",revision=42,assignments=[a],status="optimal"))
            return result(not e.is_equilibrium,equilibrium=e.is_equilibrium,assignments=e.active_assignments)
        await log.case("restart-recovery", "incomplete saved assignment cannot become current verified state", {"missing":missing},
                       "restoration rejects/quarantines incomplete IDs without inventing registry references",run,issue="RESTORE-UNVALIDATED")
    e=engine_for()
    async def stream_test():
        from api.websocket import stream_manager
        with patch.object(stream_manager,"broadcast",new_callable=AsyncMock) as broadcast:
            await e.trigger_replan()
            return result(broadcast.await_count>0,broadcast_count=broadcast.await_count)
    await log.case("streaming", "automatic engine replan publishes event", {}, "at least one broadcast for non-HTTP replan",stream_test,
                   layer="engine+mocked-broadcast",issue="AUTOMATIC-STREAM")


async def live_cases(log, base):
    async with httpx.AsyncClient(base_url=base, timeout=10, trust_env=False) as client:
        response=await client.get("/openapi.json")
        schema=response.json()
        (log.output/"openapi-live.json").write_text(json.dumps(schema,indent=2),encoding="utf-8")
        replacements={"issue_id":"REC-1050","decision_id":"DEC-803","forecast_id":"FORECAST-01","schedule_id":"SCH-841","base_id":"SCH-841","target_id":"SCH-842","run_id":"RUN-42","agent_id":"AGENT-01","approval_id":"APP-101"}
        for template, methods in schema["paths"].items():
            path=template
            for key,value in replacements.items():path=path.replace("{"+key+"}",value)
            if "get" in methods:
                async def run(path=path,template=template):
                    response=await client.get(path)
                    log.covered_operations.add("GET "+template)
                    try: data=response.json()
                    except ValueError:data=response.text[:300]
                    return result(response.status_code==200,http=response.status_code,response=data)
                await log.case("live-http", "implemented GET responds with JSON",{"path":path},"HTTP 200 JSON for existing resource",run,layer="live-network",issue="LIVE-ROUTE")
            async def wrong(path=path,template=template):
                response=await client.patch(path,json={})
                return result(response.status_code==405,http=response.status_code)
            await log.case("live-http-methods","unsupported method is rejected",{"path":path,"method":"PATCH"},"HTTP 405",wrong,layer="live-network",issue="HTTP-METHOD")
        for path in ["/api/v1/validity/decisions/AUDIT-NOT-FOUND","/api/v1/planning/schedules/AUDIT-NOT-FOUND","/api/v1/stress/runs/AUDIT-NOT-FOUND","/api/v1/agents/requests/AUDIT-NOT-FOUND",
                     "/api/v1/evidence/issues/AUDIT-NOT-FOUND/autopsy","/api/v1/forecasts/AUDIT-NOT-FOUND","/api/v1/replanning/diff/AUDIT-MISSING/AUDIT-MISSING"]:
            async def run(path=path):
                response=await client.get(path)
                return result(response.status_code==404,http=response.status_code,response=response.json())
            await log.case("live-missing-resources","unknown ID does not fabricate evidence",{"path":path},"HTTP 404 for nonexistent referenced resource",run,layer="live-network",issue="FABRICATED-RESOURCE")
        log.live_schema=schema


async def main(args):
    output=ROOT/args.output
    output.mkdir(parents=True,exist_ok=True)
    before=fingerprints()
    log=Ledger(output)
    metadata={"python":platform.python_version(),"platform":platform.platform(),"seed":26250,
              "api_base":args.api_base,"frontend_base":args.frontend_base,"source_before":before,
              "harness_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"scripts").glob("audit_*.py")}}
    try:
        await live_cases(log,args.api_base)
        await solver_cases(log)
        await verifier_cases(log)
        await telemetry_cases(log)
        await api_cases(log)
        await fault_cases(log)
        from audit_transport import transport_cases
        await transport_cases(log)
        # Browser code uses the same ledger, but a separate process/runtime avoids event-loop conflicts.
        if not args.skip_browser:
            browser_file=output/"browser-cases.json"
            completed=await asyncio.to_thread(subprocess.run,[sys.executable,str(ROOT/"scripts/audit_browser.py"),"--base",args.frontend_base,"--output",str(browser_file)],cwd=ROOT,capture_output=True,text=True,timeout=240)
            (output/"browser-run.log").write_text(completed.stdout+completed.stderr,encoding="utf-8")
            if not browser_file.exists():raise RuntimeError("Browser harness produced no ledger: "+completed.stderr[-1000:])
            for row in json.loads(browser_file.read_text(encoding="utf-8")):
                row["id"]=f"AUD-{len(log.rows)+1:04d}";log.rows.append(row)
        from audit_transport import concurrency_cases
        await concurrency_cases(log)
    finally:
        metadata["source_after"]=fingerprints()
        metadata["changed_application_files"]=[key for key,value in before.items() if metadata["source_after"].get(key)!=value]
        metadata["completed_without_browser"] = args.skip_browser
        summary=log.save(metadata)
    if summary["total"]<1000:raise SystemExit("Fewer than 1,000 cases executed")
    raise SystemExit(1 if summary["totals"].get("FAIL") else 0)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base",default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-base",default="http://localhost:3000")
    parser.add_argument("--output",default="docs/testing/2026-10-16/results")
    parser.add_argument("--skip-browser",action="store_true")
    asyncio.run(main(parser.parse_args()))
