import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { EventStore } from '../src/ingestion/store.js';
import { ReliefSimulationService } from '../src/planning/service.js';
import { IngestionService } from '../src/ingestion/service.js';
import { EVENT_TYPES } from '../src/contracts/events.js';
const NOW = Date.parse('2026-10-15T06:00:00Z');
const sources = EVENT_TYPES.map(type => ({ sourceId: `relief-${type.split('.')[0]}`, types: [type] }));
function setup(t, options = {}) {
  let time = NOW;
  const store = new EventStore({ path: ':memory:', now: () => time, ...options });
  const service = new ReliefSimulationService({store,sources,now:()=>time,annotator:{annotate:async x=>({...x,mode:'deterministic',modelsUsed:[],highlights:[]}),close:async()=>{}}});
  const ingress = new IngestionService({store,simulation:service,now:()=>time});
  t.after(async()=>{await service.close();store.close();});
  const initial=service.start({scenario:'civilian-relief',inputMode:'gateway',commandId:randomUUID()});
  return {store,service,ingress,initial,advance:ms=>{time+=ms;}};
}
function observation(initial, overrides={}) {
  return {schemaVersion:1,eventId:randomUUID(),type:'weather.observation',sourceId:'relief-weather',entityId:`input-${initial.world.runId}-SIM-CLINIC`,sequence:1,observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+60000).toISOString(),data:{temperatureC:20,windSpeedMps:25,visibilityM:1500,condition:'storm'},...overrides};
}
test('current bound gateway facts replan once and mirror outputs atomically; replays do not replan',t=>{
 const {store,service,ingress,initial}=setup(t);const e=observation(initial);
 const [r]=ingress.accept([e],sources[2]);assert.equal(r.disposition,'current');
 const s=service.snapshot();assert.equal(s.world.revision,1);assert.equal(s.plan.objective.servedPriority,7);assert.equal(s.validation.valid,true);
 assert.equal(s.inputs.bindings[0].eventId,e.eventId);assert.equal(s.nextPhase,null);assert.equal(s.coordination.decision.status,'verified');
 assert.equal(store.metrics().events,33);assert.equal(ingress.accept([e],sources[2])[0].duplicate,true);assert.equal(service.snapshot().world.revision,1);
});
test('stale, expired, unbound and nonauthoritative events cannot change the world',t=>{
 const {service,ingress,initial}=setup(t);const e=observation(initial);
 ingress.accept([e],sources[2]);
 for(const input of [observation(initial,{sequence:1}),observation(initial,{sequence:2,validUntil:new Date(NOW-1).toISOString(),observedAt:new Date(NOW-10000).toISOString()}),observation(initial,{entityId:'ordinary-airport'}),observation(initial,{entityId:`input-${randomUUID()}-SIM-CLINIC`})]) ingress.accept([input],sources[2]);
 assert.equal(service.snapshot().world.revision,1);
 const outsider={sourceId:'other-weather',types:['weather.observation']};ingress.accept([observation(initial,{sourceId:outsider.sourceId})],outsider);assert.equal(service.snapshot().world.revision,1);
});
test('invalid bound mapping rolls back mixed batch input, output, and simulation',t=>{
 const {store,service,ingress,initial}=setup(t);const n=store.metrics().events;
 const e={schemaVersion:1,eventId:randomUUID(),type:'airport.capacity',sourceId:'relief-airport',entityId:`input-${initial.world.runId}-SIM-SHELTER`,sequence:1,observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+60000).toISOString(),data:{status:'open',arrivalsPerHour:3,departuresPerHour:4}};
 assert.throws(()=>ingress.accept([e,{...e,eventId:randomUUID(),entityId:'unbound'}],sources[3]),x=>x.status===422);
 assert.equal(store.metrics().events,n);assert.equal(service.snapshot().world.revision,0);
});
test('expired input invalidates resource and rechecks proposal; refresh restores freshness',t=>{
 const {service,ingress,initial,advance}=setup(t);const e=observation(initial,{data:{temperatureC:20,windSpeedMps:5,visibilityM:10000,condition:'clear'}});
 ingress.accept([e],sources[2]);advance(60001);service.expireInputs();
 let s=service.snapshot();assert.equal(s.world.revision,2);assert.equal(s.inputs.bindings[0].expired,true);assert.equal(s.plan.objective.servedPriority,7);assert.equal(s.validation.valid,true);
 service.expireInputs();assert.equal(service.snapshot().world.revision,2);
 ingress.accept([{...e,eventId:randomUUID(),sequence:2,observedAt:new Date(NOW+60001).toISOString(),validUntil:new Date(NOW+120001).toISOString()}],sources[2]);
 s=service.snapshot();assert.equal(s.world.revision,3);assert.equal(s.inputs.bindings[0].expired,false);assert.equal(s.plan.objective.servedPriority,9);
});
test('scripted mode never consumes external bound facts',t=>{
 const {service,ingress,initial}=setup(t);
 const scripted=service.start({scenario:'civilian-relief',commandId:randomUUID(),replaceRunId:initial.world.runId});
 ingress.accept([observation(scripted)],sources[2]);assert.equal(service.snapshot().world.revision,0);
});
test('all resource mappings preserve scenario metadata and one batch is one revision', t => {
 const {service,ingress,initial}=setup(t);const ns=initial.inputs.namespace;
 const base={schemaVersion:1,eventId:randomUUID(),sequence:1,observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+60000).toISOString()};
 const aircraft={...base,type:'aircraft.status',sourceId:sources[0].sourceId,entityId:ns+'SIM-A1',data:{status:'maintenance',airportId:ns+'SIM-HUB',capacityKg:900}};
 ingress.accept([aircraft],sources[0]);assert.equal(service.snapshot().world.aircraft[0].coldStorage,true);assert.equal(service.snapshot().world.aircraft[0].status,'maintenance');
 const crew={...base,eventId:randomUUID(),type:'crew.availability',sourceId:sources[1].sourceId,entityId:ns+'SIM-C1',data:{status:'rest',qualifications:['relief-pilot'],availableFrom:new Date(NOW).toISOString(),availableUntil:new Date(NOW+120*60000).toISOString()}};
 ingress.accept([crew],sources[1]);assert.equal(service.snapshot().world.crews[0].status,'rest');
 const cargo={...base,eventId:randomUUID(),type:'cargo.request',sourceId:sources[4].sourceId,entityId:ns+'SIM-REQ-MED',data:{category:'medical',massKg:100,originAirportId:ns+'SIM-HUB',destinationAirportId:ns+'SIM-CLINIC',requestedDeliveryBy:new Date(NOW+60*60000).toISOString(),temperatureControlled:true}};
 ingress.accept([cargo],sources[4]);assert.equal(service.snapshot().world.requests[0].priority,5);assert.equal(service.snapshot().world.requests[0].massKg,100);
 const a=observation(initial),b=observation(initial,{entityId:ns+'SIM-SHELTER'});
 ingress.accept([a,b],sources[2]);const s=service.snapshot();assert.equal(s.world.revision,4);assert.equal(s.plan.assignments.length,0);assert.equal(s.inputs.bindings.length,5);assert.equal(s.validation.valid,true);
});
test('outbox capacity and DB failure roll back bound input and mirrored outputs',t=>{
 const {store,service,ingress,initial}=setup(t,{maxPending:17});
 assert.throws(()=>ingress.accept([observation(initial)],sources[2]),e=>e.status===503);
 assert.equal(store.metrics().events,16);assert.equal(service.snapshot().world.revision,0);
 store.maxPending=10000;store.db.exec("CREATE TRIGGER fail_dynamic BEFORE UPDATE ON relief_state BEGIN SELECT RAISE(ABORT,'failure'); END;");
 assert.throws(()=>ingress.accept([observation(initial)],sources[2]));
 assert.equal(store.metrics().events,16);assert.equal(service.snapshot().world.revision,0);
});
test('expiry failure makes the previous proposal explicitly historical until retry succeeds',t=>{
 const {store,service,ingress,initial,advance}=setup(t);
 ingress.accept([observation(initial)],sources[2]);advance(60001);
 store.maxPending=store.metrics().outbox.queued;
 assert.throws(()=>service.expireInputs(),e=>e.status===503);
 assert.equal(service.snapshot().planUsable,false);assert.equal(service.snapshot().inputFreshness.replanPending,true);
 store.maxPending=10000;service.expireInputs();assert.equal(service.snapshot().planUsable,true);assert.equal(service.snapshot().world.revision,2);
});
test('bounded revision budget rejects new inputs atomically and reserves final expiration',t=>{
 const {store,service,ingress,initial,advance}=setup(t);const ns=initial.inputs.namespace;
 ingress.accept([{schemaVersion:1,eventId:randomUUID(),sequence:1,type:'aircraft.status',sourceId:sources[0].sourceId,entityId:ns+'SIM-A1',observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+120000).toISOString(),data:{status:'available',airportId:ns+'SIM-HUB',capacityKg:800}}],sources[0]);
 for(let sequence=1;sequence<=18;sequence++)ingress.accept([observation(initial,{sequence})],sources[2]);
 assert.equal(service.snapshot().world.revision,19);const count=store.metrics().events;
 assert.throws(()=>ingress.accept([observation(initial,{sequence:19})],sources[2]),e=>e.code==='SIMULATION_REVISION_CAPACITY');
 assert.equal(store.metrics().events,count);advance(60001);service.expireInputs();
 const s=service.snapshot();assert.equal(s.world.revision,20);assert.ok(s.inputs.bindings.every(b=>b.expired));assert.equal(s.inputs.bindings.find(b=>b.type==='aircraft.status').expiryReason,'revision-capacity');assert.equal(s.validation.valid,true);
});
test('aircraft maintenance is checked at receipt time and future due dates limit mirrored validity',t=>{
 const {service,store,ingress,initial,advance}=setup(t);const ns=initial.inputs.namespace;
 const make=(sequence,observedAt,due)=>({schemaVersion:1,eventId:randomUUID(),sequence,sourceId:sources[0].sourceId,type:'aircraft.status',entityId:ns+'SIM-A1',observedAt:new Date(observedAt).toISOString(),validUntil:new Date(NOW+120000).toISOString(),data:{status:'available',airportId:ns+'SIM-HUB',capacityKg:800,maintenanceDueAt:new Date(due).toISOString()}});
 ingress.accept([make(1,NOW-60000,NOW-30000)],sources[0]);assert.equal(service.snapshot().world.aircraft[0].status,'maintenance');
 ingress.accept([make(2,NOW,NOW+30000)],sources[0]);let mirrored=store.listState({type:'aircraft.status',entityId:`relief-${initial.world.runId}-SIM-A1`}).items[0].event;
 assert.equal(mirrored.validUntil,new Date(NOW+30000).toISOString());assert.equal(mirrored.data.maintenanceDueAt,new Date(NOW+30000).toISOString());
 advance(30001);service.expireInputs();assert.ok(!service.snapshot().plan.assignments.some(a=>a.aircraftId==='SIM-A1'));
 mirrored=store.listState({type:'aircraft.status',entityId:`relief-${initial.world.runId}-SIM-A1`}).items[0];assert.equal(mirrored.freshness,'expired');
});
test('mirrors retain binding TTL, weather temperature and original slot anchor after time passes',t=>{
 const {service,store,ingress,initial,advance}=setup(t);const ns=initial.inputs.namespace;advance(10*60000);
 const now=NOW+10*60000;
 const e=observation(initial,{observedAt:new Date(now).toISOString(),validUntil:new Date(now+60000).toISOString(),data:{temperatureC:31,windSpeedMps:5,visibilityM:10000,condition:'clear'}});
 ingress.accept([e],sources[2]);
 const mirror=store.listState({type:'weather.observation',entityId:`relief-${initial.world.runId}-SIM-CLINIC`}).items[0].event;
 assert.equal(mirror.validUntil,e.validUntil);assert.equal(mirror.data.temperatureC,31);
 const crew={schemaVersion:1,eventId:randomUUID(),sequence:1,type:'crew.availability',sourceId:sources[1].sourceId,entityId:ns+'SIM-C1',observedAt:new Date(now).toISOString(),validUntil:new Date(now+60000).toISOString(),data:{status:'available',qualifications:['relief-pilot'],availableFrom:new Date(NOW+30*60000).toISOString(),availableUntil:new Date(NOW+120*60000).toISOString()}};
 ingress.accept([crew],sources[1]);const mirrored=store.listState({type:'crew.availability',entityId:`relief-${initial.world.runId}-SIM-C1`}).items[0].event;
 assert.equal(mirrored.data.availableFrom,crew.data.availableFrom);assert.equal(mirrored.data.availableUntil,crew.data.availableUntil);
 advance(60001);service.expireInputs();assert.equal(store.listState({type:'weather.observation',entityId:`relief-${initial.world.runId}-SIM-CLINIC`}).items[0].freshness,'expired');
});
test('restart with expired input and full persisted outbox starts historical and can recover', async t => {
 const {store,service,ingress,initial,advance}=setup(t);
 ingress.accept([observation(initial)],sources[2]);await service.close();advance(60001);store.maxPending=store.metrics().outbox.queued;
 let recovered;
 assert.doesNotThrow(()=>{recovered=new ReliefSimulationService({store,sources,now:()=>store.now(),annotator:{annotate:async x=>({...x,mode:'deterministic'}),close:async()=>{}}});});
 assert.equal(recovered.snapshot().planUsable,false);assert.equal(recovered.snapshot().inputFreshness.replanPending,true);
 store.maxPending=10000;recovered.expireInputs();assert.equal(recovered.snapshot().planUsable,true);assert.equal(recovered.snapshot().world.revision,2);await recovered.close();
});
