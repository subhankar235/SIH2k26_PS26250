"""Recovery, malformed-event and isolated real-Kafka tests for the audit runner."""
import asyncio
import copy
import json
import subprocess
import sys
import uuid
from dataclasses import asdict, replace
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


async def transport_cases(log):
    # Imported lazily so the main runner retains a single app/registry instance.
    from audit_system import ROOT, MemoryStorage, world, engine_for, cancel_engine, result
    from transport.consumer import IngestionEventConsumer

    async def cli():
        proc=await asyncio.to_thread(subprocess.run,[sys.executable,"-m","services.simulator.injector","--help"],cwd=ROOT,capture_output=True,text=True,timeout=15)
        return result(proc.returncode==0,exit_code=proc.returncode,stdout=proc.stdout[:1500],stderr=proc.stderr[:1500])
    await log.case("simulator-cli","scenario CLI help works",{},"--help exits zero without running or changing a scenario",cli,layer="subprocess",issue="SIMULATOR-CLI")

    for kind,value in [("duty",None),("duty","bad"),("duty",[]),("capacity",-1),("capacity","bad"),("capacity",{}),("weather",{}),("type",7),("type",None),("data",[]),("data","bad")]:
        async def run(kind=kind,value=value):
            e=engine_for()
            event=dict(type="aircraft.status",entityId="A0",data={"status":"available"})
            if kind=="duty":event.update(type="crew.availability",entityId="C0",data={"dutyHoursLeft":value})
            elif kind=="capacity":event["data"]["capacityKg"]=value
            elif kind=="weather":event.update(type="weather.observation",entityId="CLINIC",data={"condition":value})
            elif kind=="type":event["type"]=value
            else:event["data"]=value
            before=asdict(e.airframes["A0"]),asdict(e.crews["C0"]),asdict(e.corridors["R0"])
            try:
                res = await e.ingest_event(event)
                rejected = (res is False)
            except (ValueError,TypeError,AttributeError):
                # Exceptions here still fail graceful-validation expectations, but fixtures are cleaned up.
                await cancel_engine(e)
                return result(False,error="unstructured exception",input=event)
            await cancel_engine(e)
            after=asdict(e.airframes["A0"]),asdict(e.crews["C0"]),asdict(e.corridors["R0"])
            return result(rejected and before==after,state_changed=before!=after,rejected=rejected,input=event)
        await log.case("event-validation","malformed event is rejected atomically",dict(field=kind,value=value),
                       "structured validation rejection, no state mutation or consumer-loop crash",run,layer="isolated-engine",issue="EVENT-VALIDATION")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes
    def websocket():
        e=engine_for()
        routes.set_engine(e)
        app=FastAPI();app.include_router(routes.router)
        with TestClient(app) as client:
            with client.websocket_connect("/ws/magi/stream") as ws:
                response=client.post("/api/v1/replan")
                data=ws.receive_json()
                return result(response.status_code==200 and data["type"]=="REPLAN_EVENT" and data["revision"]==e.revision,event=data)
    await log.case("streaming","WebSocket receives explicit manual replan",{},"REPLAN_EVENT with matching revision over actual ASGI WebSocket",websocket,
                   layer="ASGI-WebSocket+memory-storage",issue="MANUAL-STREAM")

    from api import server
    class RecoveryStorage(MemoryStorage):
        async def init_db(self):pass
        async def get_latest_plan(self):
            return SimpleNamespace(run_id="audit-restored",revision=42,status="optimal",served_priority=5,threat_risk_score=0,
                                   assignments=[dict(mission_id="M0",airframe_id="A0",crew_id="C0",corridor_id="R0",slot=0)],unserved=[])
    class NoBroker:
        def __init__(self,engine):self.engine=engine
        async def start(self):pass
        async def consume_loop(self):await asyncio.Future()
        async def stop(self):pass
    async def restore():
        with patch.object(server,"StorageEngine",RecoveryStorage),patch("transport.consumer.IngestionEventConsumer",NoBroker):
            async with server.lifespan(server.app):
                e=routes.get_engine()
                ids=all(a["mission_id"] in e.missions and a["airframe_id"] in e.airframes and a["crew_id"] in e.crews and a["corridor_id"] in e.corridors for a in e.active_assignments)
                return result(e.revision==42 and ids,revision=e.revision,registry_references_resolve=ids,active_assignments=e.active_assignments)
    await log.case("restart-recovery","lifespan restores saved world and assignments consistently",{},"revision restored together with matching resource/mission world, or rejected as historical",restore,
                   layer="real-lifespan+injected-storage-and-broker",issue="RESTORE-WORLD-DRIFT")

    # Real broker integration is confined to one UUID-named topic and its own consumer group.
    from aiokafka import AIOKafkaProducer
    from aiokafka.admin import AIOKafkaAdminClient,NewTopic
    topic="codex-audit-"+uuid.uuid4().hex
    admin=AIOKafkaAdminClient(bootstrap_servers="127.0.0.1:29092",request_timeout_ms=5000)
    producer=None;consumer=None;task=None;created=False
    try:
        await admin.start()
        await admin.create_topics([NewTopic(topic,num_partitions=1,replication_factor=1)])
        created=True
        producer=AIOKafkaProducer(bootstrap_servers="127.0.0.1:29092",request_timeout_ms=5000)
        await producer.start()
        e=engine_for()
        consumer=IngestionEventConsumer(bootstrap_servers="127.0.0.1:29092",topics=[topic],group_id=topic,engine=e)
        await consumer.start()
        # Drive assignment before sending, because this implementation resets new groups to latest.
        for _ in range(60):
            await consumer.consumer.getmany(timeout_ms=100)
            if consumer.consumer.assignment():break
        task=asyncio.create_task(consumer.consume_loop())
        for name,event,expected in [
            ("maintenance",dict(type="aircraft.status",entityId="A0",data={"status":"maintenance"}),"maintenance"),
            ("capacity zero",dict(type="aircraft.status",entityId="A0",data={"status":"available","capacityKg":0}),0),
            ("duty zero",dict(type="crew.availability",entityId="C0",data={"status":"available","dutyHoursLeft":0}),0),
            ("destination storm",dict(type="weather.observation",entityId="CLINIC",data={"condition":"storm"}),"storm"),
            ("expired maintenance",dict(type="aircraft.status",entityId="A0",observedAt="2000-01-01T00:00:00Z",validUntil="2000-01-02T00:00:00Z",data={"status":"maintenance"}),"available"),
        ]:
            async def run(name=name,event=event,expected=expected):
                await cancel_engine(e)
                m,a,c,r=world();e.initialize_world(a,c,r,m);e.establish_initial_equilibrium();e._pending_events.clear()
                await producer.send_and_wait(topic,json.dumps(event).encode())
                for _ in range(60):
                    if e._pending_events or task.done():break
                    await asyncio.sleep(0.025)
                if name=="capacity zero":actual=e.airframes["A0"].capacity_kg
                elif name=="duty zero":actual=e.crews["C0"].duty_hours_left
                elif name=="destination storm":actual=e.corridors["R0"].weather_condition
                else:actual=e.airframes["A0"].status
                return result(actual==expected and bool(e._pending_events),observed=actual,expected=expected,consumed=len(e._pending_events))
            await log.case("real-kafka","broker -> application consumer: "+name,event,"expected isolated-engine state after real broker delivery",run,
                           layer="real-Kafka+application-consumer+memory-storage",issue="KAFKA-EVENT-VALIDITY")
        async def poison():
            await producer.send_and_wait(topic,b'{invalid-json')
            await asyncio.sleep(0.2)
            if task.done():
                try:task.result()
                except Exception as exc:return result(False,consumer_stopped=True,exception=type(exc).__name__)
            return result(True,consumer_stopped=False)
        await log.case("real-kafka","malformed JSON cannot kill consumption",{"value":"{invalid-json"},"consumer survives/quarantines poison record",poison,
                       layer="real-Kafka+application-consumer",issue="KAFKA-POISON-RECORD")
        await cancel_engine(e)
    except Exception as exc:
        await log.case("real-kafka","isolated broker integration setup",{},"broker available and unique topic can be created",lambda:result(False,error=type(exc).__name__,message=str(exc)[:500]),
                       layer="real-Kafka-infrastructure",issue="KAFKA-INFRASTRUCTURE")
    finally:
        if task and not task.done():task.cancel()
        if task:await asyncio.gather(task,return_exceptions=True)
        if consumer:await consumer.stop()
        if producer:await producer.stop()
        if created and topic.startswith("codex-audit-") and len(topic)==44:
            await admin.delete_topics([topic])
        await admin.close()


async def concurrency_cases(log):
    from audit_system import MemoryStorage, engine_for, cancel_engine, result
    for count in [2,3,4]:
        class DelayedStorage(MemoryStorage):
            async def save_plan(self,value):
                self.plans.append(copy.deepcopy(value))
                identity=f"audit-plan-{len(self.plans)}"
                await asyncio.sleep(0.01)  # Exercise a real await boundary like a database write.
                return SimpleNamespace(id=identity)
        async def run(count=count):
            store=DelayedStorage();e=engine_for(storage=store)
            await asyncio.gather(*(e.trigger_replan() for _ in range(count)))
            revisions={f"audit-plan-{i+1}":p['revision'] for i,p in enumerate(store.plans)}
            wrong=[dict(plan_id=t['plan_id'],transcript_revision=t['revision'],plan_revision=revisions[t['plan_id']])
                   for t in store.transcripts if t['revision']!=revisions[t['plan_id']]]
            return result(not wrong,plans=revisions,mismatched_transcripts=wrong[:8],mismatch_count=len(wrong))
        await log.case("concurrency","concurrent replans preserve transcript revision identity",{"concurrent_replans":count},
                       "every transcript revision matches its persisted plan despite interleaved storage awaits",run,
                       layer="engine+injected-storage-latency",issue="CONCURRENT-REVISION-DRIFT")
    for capacity in [0,500,999]:
        async def run(capacity=capacity):
            e=engine_for()
            event=dict(eventId="audit-replay",sourceId="audit-source",sequence=1,type="aircraft.status",entityId="A0",data={"status":"available","capacityKg":capacity})
            if await e.ingest_event(event):
                await cancel_engine(e);await e.trigger_replan()
            first=e.revision
            replay_broke=await e.ingest_event(copy.deepcopy(event))
            if replay_broke:
                await cancel_engine(e);await e.trigger_replan()
            return result(e.revision==first,first_revision=first,revision_after_replay=e.revision,replay_broke=replay_broke)
        await log.case("event-idempotency","same event ID cannot produce another plan revision",{"capacity":capacity,"repeated_event_id":"audit-replay"},
                       "exact replay is idempotent, with no second plan revision",run,layer="isolated-engine+memory-storage",issue="EVENT-REPLAY")


if __name__=="__main__":
    # Add only these focused checks to an already completed audit without rerunning other suites.
    import argparse
    from datetime import datetime,timezone
    from audit_system import Ledger,fingerprints
    parser=argparse.ArgumentParser(description="Append concurrency/replay checks to an existing audit ledger")
    parser.add_argument("--append-results",required=True)
    args=parser.parse_args()
    output=Path(args.append_results)
    metadata=json.loads((output/'summary.json').read_text(encoding='utf-8'))
    log=Ledger(output)
    log.rows=json.loads((output/'cases.json').read_text(encoding='utf-8'))
    log.started=metadata['started_utc']
    log.covered_operations=set(json.loads((output/'api-coverage.json').read_text(encoding='utf-8')))
    if any(row['category']=='concurrency' for row in log.rows):raise SystemExit('Concurrency cases already recorded')
    asyncio.run(concurrency_cases(log))
    for key in ['total','totals','by_category','started_utc','finished_utc']:metadata.pop(key,None)
    metadata['additional_segment_utc']=datetime.now(timezone.utc).isoformat()
    metadata['source_after']=fingerprints()
    metadata['changed_application_files']=[k for k,v in metadata['source_before'].items() if metadata['source_after'].get(k)!=v]
    metadata['harness_extension']='audit_transport.py concurrency_cases; see additional_segment_utc'
    log.save(metadata)
