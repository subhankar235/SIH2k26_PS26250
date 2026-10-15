import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {EventStore} from '../src/ingestion/store.js';
import {ReliefSimulationService} from '../src/planning/service.js';
import {EVENT_TYPES} from '../src/contracts/events.js';
const NOW=Date.parse('2026-10-15T06:00:00Z');
const sources=EVENT_TYPES.map(type=>({sourceId:`relief-${type.split('.')[0]}`,types:[type]}));
function setup(t,provider){const store=new EventStore({path:':memory:',now:()=>NOW});const service=new ReliefSimulationService({store,sources,now:()=>NOW,weatherProvider:provider,annotator:{annotate:async x=>({...x,mode:'deterministic'}),close:async()=>{}}});t.after(async()=>{await service.close();store.close();});const initial=service.start({scenario:'civilian-relief',inputMode:'gateway',commandId:randomUUID()});return{store,service,initial};}
const result=()=>({data:{temperatureC:20,windSpeedMps:25,visibilityM:1500,condition:'storm'},observedAt:new Date(NOW).toISOString(),validUntil:new Date(NOW+60000).toISOString(),provenance:{provider:'Open-Meteo',location:'delhi',latitude:28.6139,longitude:77.209,fetchedAt:new Date(NOW).toISOString(),weatherTime:new Date(NOW).toISOString(),visibilityTime:new Date(NOW).toISOString()}});
const command=initial=>({commandId:randomUUID(),runId:initial.world.runId,expectedRevision:0,airportId:'SIM-CLINIC',location:'delhi'});
test('live weather applies through gateway transaction and exact commands replay without refetch',async t=>{let calls=0;const{service,initial,store}=setup(t,{fetch:async()=>{calls++;return result();},close:async()=>{}});const cmd=command(initial);const r=await service.weather(cmd);assert.equal(r.world.revision,1);assert.equal(r.plan.objective.servedPriority,7);assert.equal(r.weatherFeed.status,'ready');assert.equal(store.metrics().events,33);const replay=await service.weather(cmd);assert.equal(replay.command.replayed,true);assert.equal(calls,1);assert.throws(()=>service.start({scenario:'civilian-relief',commandId:cmd.commandId}),e=>e.code==='SIMULATION_COMMAND_CONFLICT');});
test('provider failure persists explicit degradation and no guessed input or plan revision',async t=>{const{service,initial,store}=setup(t,{fetch:async()=>{throw Object.assign(new Error('secret upstream'),{code:'WEATHER_UNAVAILABLE'});},close:async()=>{}});const r=await service.weather(command(initial));assert.equal(r.weatherFeed.status,'degraded');assert.equal(r.weatherFeed.errorCode,'WEATHER_UNAVAILABLE');assert.equal(r.world.revision,0);assert.equal(store.metrics().events,16);assert.ok(!JSON.stringify(r).includes('secret upstream'));});
test('late weather is discarded after run replacement',async t=>{let release;const{service,initial,store}=setup(t,{fetch:()=>new Promise(r=>{release=r;}),close:async()=>{}});const pending=service.weather(command(initial));const newer=service.start({scenario:'civilian-relief',inputMode:'gateway',replaceRunId:initial.world.runId,commandId:randomUUID()});release(result());await assert.rejects(pending,e=>e.code==='SIMULATION_REVISION_CONFLICT');assert.equal(service.snapshot().world.runId,newer.world.runId);assert.equal(service.snapshot().world.revision,0);assert.equal(store.metrics().events,32);assert.equal(service.snapshot().weatherFeed,undefined);});
test('concurrent same command shares fetch; different command is rejected',async t=>{let release,calls=0;const{service,initial}=setup(t,{fetch:()=>{calls++;return new Promise(r=>{release=r;});},close:async()=>{}});const cmd=command(initial);const a=service.weather(cmd),b=service.weather(cmd);await assert.rejects(service.weather(command(initial)),e=>e.code==='WEATHER_BUSY');release(result());const [x,y]=await Promise.all([a,b]);assert.equal(x.world.revision,y.world.revision);assert.equal(calls,1);});
test('restart marks an interrupted pending weather command as degraded', async t => {
 const {store,service,initial}=setup(t,{fetch:async()=>result(),close:async()=>{}});
 const current=service.snapshot();current.weatherFeed={status:'pending',runId:initial.world.runId,revision:0,commandId:randomUUID(),airportId:'SIM-CLINIC',location:'delhi'};
 service.write(current);await service.close();
 const recovered=new ReliefSimulationService({store,sources,now:()=>NOW,annotator:{annotate:async x=>({...x,mode:'deterministic'}),close:async()=>{}}});
 t.after(()=>recovered.close());assert.equal(recovered.snapshot().weatherFeed.status,'degraded');assert.equal(recovered.snapshot().weatherFeed.errorCode,'WEATHER_INTERRUPTED');
});
test('weather finalization failure is durably replayed without refetch',async t=>{
 let calls=0;const{service,initial,store}=setup(t,{fetch:async()=>{calls++;return result();},close:async()=>{}});const cmd=command(initial);store.maxPending=17;
 await assert.rejects(service.weather(cmd),e=>e.code==='BACKLOG_FULL');store.maxPending=10000;
 await assert.rejects(service.weather(cmd),e=>e.code==='BACKLOG_FULL');assert.equal(calls,1);assert.equal(service.snapshot().world.revision,0);assert.equal(store.metrics().events,16);
});
test('weather cannot publish on behalf of a removed source authority',async t=>{
 let calls=0;const{service,initial}=setup(t,{fetch:async()=>{calls++;return result();},close:async()=>{}});
 service.sources=sources.map(s=>s.sourceId==='relief-weather'?{...s,sourceId:'replacement-weather'}:s);
 await assert.rejects(service.weather(command(initial)),e=>e.code==='SIMULATION_SOURCE_AUTHORITY_CHANGED');assert.equal(calls,0);
});
