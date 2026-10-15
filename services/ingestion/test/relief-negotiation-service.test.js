import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { EventStore } from '../src/ingestion/store.js';
import { ReliefSimulationService } from '../src/planning/service.js';
import { IngestionService } from '../src/ingestion/service.js';
import { runReliefNegotiation } from '../src/agents/negotiation.js';
import { EVENT_TYPES } from '../src/contracts/events.js';
const NOW=Date.parse('2026-10-15T06:00:00Z');
const sources=EVENT_TYPES.map(type=>({sourceId:`test-${type.split('.')[0]}`,types:[type]}));
function setup(t,options={}){
 let now=NOW;const store=new EventStore({path:':memory:',now:()=>now});
 const service=new ReliefSimulationService({store,sources,now:()=>now,annotator:{annotate:async x=>({...x,mode:'deterministic',modelsUsed:[],highlights:[]}),close:async()=>{}},...options});
 t.after(async()=>{await service.close();store.close();});return{store,service,ingress:new IngestionService({store,simulation:service,now:()=>now}),advance:ms=>{now+=ms;}};
}
test('service automatically negotiates each revision, persists settings and replays exact transcripts',t=>{
 const{service}=setup(t),command={scenario:'civilian-relief',commandId:randomUUID(),negotiation:{maxRounds:2,maxMessages:400}};
 const s=service.start(command);assert.equal(s.negotiation.revision,0);assert.equal(s.negotiation.outcome.verified,true);
 assert.ok(s.negotiation.messages.some(m=>m.kind==='counterproposal'));assert.deepEqual(service.start(command).negotiation,s.negotiation);
 const next=service.step({commandId:randomUUID(),runId:s.world.runId,expectedRevision:0,phase:'weather-change'});
 assert.equal(next.negotiation.revision,1);assert.equal(next.negotiation.settings.maxRounds,2);
 const oldIds=new Set(s.negotiation.messages.map(m=>m.id));assert.ok(next.negotiation.messages.every(m=>!oldIds.has(m.id)));assert.equal(next.validation.valid,true);
});
test('gateway and TTL revisions renegotiate with no surviving stale reservations',t=>{
 const{service,ingress,advance}=setup(t);const s=service.start({scenario:'civilian-relief',inputMode:'gateway',commandId:randomUUID()});
 ingress.accept([{schemaVersion:1,eventId:randomUUID(),sequence:1,sourceId:sources[2].sourceId,type:'weather.observation',entityId:s.inputs.namespace+'SIM-CLINIC',observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+60000).toISOString(),data:{temperatureC:24,windSpeedMps:25,visibilityM:1500,condition:'storm'}}],sources[2]);
 assert.equal(service.snapshot().negotiation.revision,1);assert.equal(service.snapshot().negotiation.outcome.finalServedPriority,7);
 advance(60001);service.expireInputs();const final=service.snapshot();assert.equal(final.negotiation.revision,2);assert.equal(final.negotiation.outcome.verified,true);assert.equal(final.validation.valid,true);
});
test('disabled negotiation is explicit and remains disabled across phases',t=>{
 const{service}=setup(t);let s=service.start({scenario:'civilian-relief',commandId:randomUUID(),negotiation:{enabled:false}});
 assert.equal(s.negotiation.status,'disabled');assert.equal(s.negotiation.messages.length,0);assert.equal(s.plan.objective.servedPriority,9);
 s=service.step({commandId:randomUUID(),runId:s.world.runId,expectedRevision:0,phase:'weather-change'});assert.equal(s.negotiation.status,'disabled');
});
test('policy faults use explicit unseeded deterministic fallback with a verified plan',t=>{
 const{service}=setup(t,{negotiator:()=>{throw new Error('untrusted agent failure');}});
 const s=service.start({scenario:'civilian-relief',commandId:randomUUID()});assert.equal(s.negotiation.status,'failed');assert.equal(s.negotiation.outcome.status,'deterministic-fallback');assert.equal(s.validation.valid,true);assert.equal(s.plan.objective.servedPriority,9);assert.ok(!JSON.stringify(s).includes('untrusted agent failure'));
});
test('negotiation cannot survive a rolled-back state/outbox transaction',t=>{
 const{service,store}=setup(t);store.db.exec("CREATE TRIGGER fail_neg_state BEFORE INSERT ON relief_state BEGIN SELECT RAISE(ABORT,'failure'); END;");
 assert.throws(()=>service.start({scenario:'civilian-relief',commandId:randomUUID()}));assert.equal(store.metrics().events,0);assert.deepEqual(service.snapshot(),{status:'idle'});
});

test('fabricated consensus and asynchronous policy faults cannot masquerade as agreement',async t=>{
 for(const negotiator of [
  w=>({...runReliefNegotiation(w),status:'agreed',messages:[],assignments:[],requests:[],agentStates:[]}),
  async()=>{throw new Error('async policy fault');},
 ]) {
  const{service}=setup(t,{negotiator});const s=service.start({scenario:'civilian-relief',commandId:randomUUID()});
  assert.equal(s.negotiation.status,'failed');assert.equal(s.negotiation.outcome.status,'deterministic-fallback');assert.equal(s.validation.valid,true);
 }
 await new Promise(resolve=>setImmediate(resolve));
});
test('policies receive detached world and prior-plan inputs',t=>{
 const{service}=setup(t,{negotiator:(w,options)=>{w.requests[0].priority=999;options.settings.maxRounds=8;return runReliefNegotiation(w,options);}});
 const s=service.start({scenario:'civilian-relief',commandId:randomUUID()});assert.equal(s.world.requests[0].priority,5);assert.equal(s.negotiation.status,'failed');assert.equal(s.plan.objective.servedPriority,9);assert.equal(s.negotiation.settings.maxRounds,4);
});
