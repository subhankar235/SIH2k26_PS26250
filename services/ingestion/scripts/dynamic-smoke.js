import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { spawn } from 'node:child_process';
import { startServer } from '../src/server.js';
import { runConsumer } from '../src/transport/consumer-cli.js';
import { validateReliefNegotiationReport } from '../src/agents/negotiation.js';
import { createReliefWorld } from '../src/planning/world.js';
const options=new Set(process.argv.slice(2));
if([...options].some(x=>!['--live-weather','--browser'].includes(x)))throw new Error('Usage: dynamic-smoke.js [--live-weather] [--browser]');
const brokers=process.env.KAFKA_TEST_BROKERS||process.env.KAFKA_BROKERS;
if(!brokers)throw new Error('Dynamic pipeline smoke requires a real local test broker.');
const id=randomUUID(),port=31875;
const env={...process.env,HOST:'127.0.0.1',PORT:String(port),KAFKA_BROKERS:brokers,RELIEF_AI_MODE:'deterministic',INGESTION_DB_PATH:`var/dynamic-smoke-${id}.sqlite`,CONSUMER_DB_PATH:`var/dynamic-reader-${id}.sqlite`,CONSUMER_GROUP_ID:`dynamic-smoke-${id}`};
const base=`http://127.0.0.1:${port}`;
let runtime,reader;
async function request(path,body,token=env.INGESTION_ADMIN_TOKEN){
 const response=await fetch(base+path,{method:body?'POST':'GET',redirect:'error',headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 const result=await response.json();assert.ok(response.ok,`Request failed: ${result.error?.code??response.status}`);return result;
}
function checkNegotiation(snapshot) {
 assert.equal(snapshot.negotiation.runId,snapshot.world.runId);assert.equal(snapshot.negotiation.revision,snapshot.world.revision);
 assert.equal(snapshot.negotiation.outcome.verified,true);assert.ok(snapshot.negotiation.messages.length<=512);
 // The persisted report was already audited with its actual prior plan during commit.
 const known=new Set(snapshot.plan.agentReports.flatMap(r=>r.findings.map(f=>f.id)));
 assert.ok(snapshot.negotiation.messages.every(m=>m.findingIds.every(id=>known.has(id))));
}
async function until(predicate){const deadline=Date.now()+25000;while(!predicate()){if(Date.now()>deadline)throw new Error('Dynamic pipeline wait timed out.');await delay(100);}}
try {
 runtime=await startServer(env);reader=await runConsumer(env);
 const {aircraft,crews,airports,weather,routes,requests}=createReliefWorld();
 const state=await request('/v1/simulation/start',{scenario:'civilian-relief',inputMode:'gateway',configuration:{aircraft,crews,airports,weather,routes,requests},commandId:randomUUID()});
 checkNegotiation(state);
 for(const kind of ['proposal','reject','bid','counterproposal','accept','commit'])assert.ok(state.negotiation.messages.some(m=>m.kind===kind),kind);
 assert.equal(validateReliefNegotiationReport(state.world,state.negotiation).valid,true);
 const runId=state.world.runId,namespace=state.inputs.namespace;
 const source=JSON.parse(env.INGESTION_SOURCES_JSON).find(s=>s.sourceId===state.inputs.authorities['weather.observation']);
 const observation=(airportId,sequence,bad=false,ttl=120000)=>{const now=Date.now();return{schemaVersion:1,eventId:randomUUID(),sourceId:source.sourceId,type:'weather.observation',entityId:namespace+airportId,sequence,observedAt:new Date(now).toISOString(),validUntil:new Date(now+ttl).toISOString(),data:{temperatureC:24,windSpeedMps:bad?25:5,visibilityM:bad?1500:10000,condition:bad?'storm':'clear'}};};
 const first=observation('SIM-CLINIC',1,true);
 await request('/v1/events',first,source.token);assert.equal((await request('/v1/events',first,source.token)).duplicate,true);
 assert.equal(runtime.simulation.snapshot().world.revision,1);assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority,7);checkNegotiation(runtime.simulation.snapshot());
 await request('/v1/events/batch',{events:[observation('SIM-CLINIC',2,false,2000),observation('SIM-SHELTER',1,true)]},source.token);
 assert.equal(runtime.simulation.snapshot().world.revision,2);assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority,6);checkNegotiation(runtime.simulation.snapshot());
 await until(()=>runtime.simulation.snapshot().world.revision===3);
 assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority,0);assert.equal(runtime.simulation.snapshot().planUsable,true);checkNegotiation(runtime.simulation.snapshot());
 const expiredMirror=runtime.store.listState({type:'weather.observation',entityId:`relief-${runId}-SIM-CLINIC`}).items[0];assert.equal(expiredMirror.freshness,'expired');
 await request('/v1/events/batch',{events:[observation('SIM-CLINIC',3),observation('SIM-SHELTER',2)]},source.token);
 assert.equal(runtime.simulation.snapshot().world.revision,4);assert.equal(runtime.simulation.snapshot().plan.objective.servedPriority,9);assert.equal(runtime.simulation.snapshot().validation.valid,true);
 assert.equal(runtime.store.metrics().events,84);
 if(options.has('--live-weather')){
  const command={commandId:randomUUID(),runId,expectedRevision:4,airportId:'SIM-HUB',location:'delhi'};
  const live=await request('/v1/simulation/weather',command);assert.equal(live.weatherFeed.status,'ready');assert.equal(live.world.revision,5);assert.equal(live.validation.valid,true);checkNegotiation(live);
  const replay=await request('/v1/simulation/weather',command);assert.equal(replay.command.replayed,true);
  console.log(JSON.stringify({publicWeather:live.weatherFeed.provenance,revision:live.world.revision,verified:live.validation.valid}));
 }
 while(runtime.store.metrics().outbox.queued)assert.equal((await runtime.publisher.flush()).failed,0);
 const expected=runtime.store.metrics().events;
 const count=()=>reader.store.db.prepare('SELECT COUNT(*) AS n FROM consumer_events WHERE entity_id LIKE ? OR entity_id LIKE ?').get(`relief-${runId}-%`,`input-${runId}-%`).n;
 await until(()=>count()===expected);assert.equal(runtime.store.metrics().outbox.published,expected);
 const sequence=reader.store.latest({limit:1000}).find(r=>r.event.entityId===`relief-${runId}-SIM-CLINIC`&&r.event.type==='weather.observation').event.sequence;
 assert.equal(sequence,runtime.simulation.snapshot().world.revision+1);
 await reader.stop();reader=await runConsumer(env);assert.equal(count(),expected);
 const savedNegotiation=JSON.stringify(runtime.simulation.snapshot().negotiation);
 await runtime.close();runtime=await startServer(env);
 assert.equal(JSON.stringify(runtime.simulation.snapshot().negotiation),savedNegotiation);checkNegotiation(runtime.simulation.snapshot());
 console.log(JSON.stringify({negotiation:'passed',rounds:state.negotiation.roundsCompleted,messages:state.negotiation.messages.length,serviceRestart:true}));
 console.log(JSON.stringify({dynamicPipeline:'passed',revisions:runtime.simulation.snapshot().world.revision+1,events:expected,replayedSource:true,automaticExpiry:true,readerRestart:true}));
 if(options.has('--browser'))await new Promise((resolve,reject)=>{
  const child=spawn('python',['scripts/dynamic-browser-smoke.py'],{env:{...env,MONITOR_TEST_URL:base},stdio:'inherit'});
  child.once('error',reject);child.once('exit',code=>code===0?resolve():reject(new Error('Dynamic browser smoke failed.')));
 });
} finally {
 const results=await Promise.allSettled([reader?.stop(),runtime?.close()]);
 if(results.some(r=>r.status==='rejected')){process.exitCode=1;console.error('Dynamic smoke cleanup failed.');}
}
