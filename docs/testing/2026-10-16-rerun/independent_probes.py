"""Additional behavioral checks; isolated state, no application changes.

Run from the repository root: python docs/testing/2026-10-16-rerun/independent_probes.py
"""
import asyncio
import copy
import json
import math
import sys
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_system import engine_for, world, cancel_engine

ROWS = []


async def record(name, expected, fn):
    try:
        passed, actual = await fn()
    except Exception as exc:
        passed, actual = False, {'exception': type(exc).__name__, 'message': str(exc),
                                 'traceback': traceback.format_exc(limit=3)}
    ROWS.append(dict(id=f'PROBE-{len(ROWS)+1:02d}', name=name, expected=expected,
                     status='PASS' if passed else 'FAIL', actual=actual))


async def main():
    async def missing_world():
        e = engine_for()
        a = dict(mission_id='UNKNOWN-MISSION', airframe_id='UNKNOWN-AIRCRAFT',
                 crew_id='UNKNOWN-CREW', corridor_id='UNKNOWN-CORRIDOR', slot=0)
        e.apply_restored_plan(SimpleNamespace(assignments=[a], status='optimal'))
        invented = {k: k in registry for k, registry in [
            ('UNKNOWN-MISSION', e.missions), ('UNKNOWN-AIRCRAFT', e.airframes),
            ('UNKNOWN-CREW', e.crews), ('UNKNOWN-CORRIDOR', e.corridors)]}
        return not e.is_equilibrium and not any(invented.values()), dict(
            is_equilibrium=e.is_equilibrium, invented_registry_entries=invented,
            aircraft=asdict(e.airframes['UNKNOWN-AIRCRAFT']) if invented['UNKNOWN-AIRCRAFT'] else None)
    await record('restore unknown registry references', 'quarantine unknown resources; never invent operational capability', missing_world)

    async def restored_metadata():
        e = engine_for(world(minutes=180))
        a = dict(e.active_assignments[0], slot=2, estimated_arrival_slot=5, threat_risk=0.6)
        e.apply_restored_plan(SimpleNamespace(assignments=[a], status='optimal'))
        actual = asdict(e.active_plan.assignments[0])
        return actual['estimated_arrival_slot'] == 5 and actual['threat_risk'] == 0.6, actual
    await record('restore assignment timing and risk', 'persisted arrival slot=5 and risk=0.6 survive restoration', restored_metadata)

    async def closure(weather):
        e = engine_for()
        try:
            await e.ingest_event(dict(type='airport.status', entityId='HUB', data={'status':'closed'}))
            await cancel_engine(e)
            await e.trigger_replan()
            after_close = len(e.active_assignments)
            event = dict(type='weather.update', entityId='HUB', data={'condition':'clear'}) if weather else dict(
                type='airport.status', entityId='HUB', data={'status':'open'})
            broke = await e.ingest_event(event)
            await cancel_engine(e)
            await e.trigger_replan()
            actual = dict(after_close=after_close, after_followup=len(e.active_assignments),
                          closed_airports=sorted(e.closed_airports), corridor_weather=e.corridors['R0'].weather_condition,
                          followup_scheduled_replan=broke)
            return (not e.active_assignments if weather else bool(e.active_assignments)), actual
        finally:
            await cancel_engine(e)
    await record('clear weather while airport remains closed', 'closed airport remains unavailable after weather clearance', lambda: closure(True))
    await record('airport reopening restores feasible route', 'sole mission becomes serviceable after explicit airport reopening', lambda: closure(False))

    async def hazardous():
        m,a,c,r = world()
        m = [replace(m[0], hazardous=True)]
        e = engine_for((m,a,c,r))
        try:
            await e.ingest_event(dict(type='cargo.updated', entityId='M0', data={'mass_kg':900}))
            return e.missions['M0'].hazardous, asdict(e.missions['M0'])
        finally:
            await cancel_engine(e)
    await record('cargo mass update preserves hazardous flag', 'hazardous=True survives unrelated mass change', hazardous)

    async def partial_crew():
        e = engine_for(world(duty=1.25))
        try:
            await e.ingest_event(dict(type='crew.updated', entityId='C0', data={'qualifications':['transport']}))
            return e.crews['C0'].duty_hours_left == 1.25, asdict(e.crews['C0'])
        finally:
            await cancel_engine(e)
    await record('partial crew update preserves remaining duty', 'omitted duty retains 1.25h instead of resetting to 12h', partial_crew)

    for field, value, typ, entity, registry, attr in [
        ('capacityKg', float('nan'), 'aircraft.updated', 'A0', 'airframes', 'capacity_kg'),
        ('maxRangeKm', float('inf'), 'aircraft.updated', 'A0', 'airframes', 'max_range_km'),
        ('dutyHoursLeft', float('inf'), 'crew.updated', 'C0', 'crews', 'duty_hours_left'),
    ]:
        async def finite(field=field, value=value, typ=typ, entity=entity, registry=registry, attr=attr):
            e = engine_for()
            before = getattr(getattr(e, registry)[entity], attr)
            try:
                returned = await e.ingest_event(dict(type=typ, entityId=entity, data={field:value}))
                after = getattr(getattr(e, registry)[entity], attr)
                return math.isfinite(after) and after == before, dict(field=field, supplied=repr(value),
                    before=before, after=repr(after), returned=returned)
            finally:
                await cancel_engine(e)
        await record(f'reject non-finite {field}', 'reject non-finite input without mutating valid state', finite)

    async def bad_risk():
        e = engine_for()
        try:
            returned = await e.ingest_event(dict(type='threat.update', entityId='R0', data={'riskScore':'not-a-number'}))
            return returned is False and e.corridors['R0'].threat_risk == 0, dict(returned=returned)
        finally:
            await cancel_engine(e)
    await record('malformed threat risk is rejected safely', 'no exception or state corruption from malformed risk', bad_risk)

    async def bad_expiry():
        e = engine_for()
        try:
            returned = await e.ingest_event(dict(type='aircraft.updated', entityId='A0', validUntil='definitely-not-a-date',
                                                 data={'capacityKg':500}))
            return e.airframes['A0'].capacity_kg == 1000, dict(returned=returned, capacity=e.airframes['A0'].capacity_kg)
        finally:
            await cancel_engine(e)
    await record('malformed event expiration is rejected', 'invalid validity metadata cannot alter operational state', bad_expiry)

    async def semantic_poison():
        from transport.consumer import IngestionEventConsumer
        class FakeRecords:
            """Only the broker iterator is doubled; application consumer and engine are real."""
            def __init__(self):
                self.messages = iter([
                    SimpleNamespace(value=dict(type='threat.update', entityId='R0', data={'riskScore':'not-a-number'})),
                    SimpleNamespace(value=dict(type='aircraft.updated', entityId='A0', data={'capacityKg':800})),
                ])
                self.stopped = False
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    raise StopAsyncIteration
            async def stop(self):
                self.stopped = True
        e = engine_for()
        consumer = IngestionEventConsumer(engine=e)
        consumer.consumer = FakeRecords()
        consumer._running = True
        error = None
        try:
            await consumer.consume_loop()
        except Exception as exc:
            error = dict(type=type(exc).__name__, message=str(exc))
        finally:
            await cancel_engine(e)
        return error is None and e.airframes['A0'].capacity_kg == 800, dict(
            exception=error, capacity_after_second_event=e.airframes['A0'].capacity_kg,
            consumer_stopped=consumer.consumer.stopped)
    await record('consumer survives semantic poison record', 'invalid risk must not prevent following valid event from being applied', semantic_poison)

    dest = Path(__file__).with_name('independent-probes.json')
    dest.write_text(json.dumps(ROWS, indent=2), encoding='utf-8')
    print(json.dumps(dict(total=len(ROWS), passed=sum(r['status']=='PASS' for r in ROWS),
                          failed=sum(r['status']=='FAIL' for r in ROWS), output=str(dest))))
    return int(any(r['status'] == 'FAIL' for r in ROWS))


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
