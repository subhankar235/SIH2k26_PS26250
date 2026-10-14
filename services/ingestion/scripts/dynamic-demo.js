import { randomUUID } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
const args=process.argv.slice(2);let configuration,liveWeather=false;
for(let i=0;i<args.length;i++){
 if(args[i]==='--weather')liveWeather=true;
 else if(args[i]==='--configuration'&&args[i+1]){const file=args[++i];if(statSync(file).size>256000)throw new Error('Configuration exceeds256KB.');configuration=JSON.parse(readFileSync(file,'utf8').replace(/^\uFEFF/,''));}
 else throw new Error('Usage: npm run relief:dynamic -- [--configuration path.json] [--weather]');
}
const base=new URL(process.env.INGESTION_DEMO_URL??'http://127.0.0.1:3100');
if(!['http:','https:'].includes(base.protocol)||!['127.0.0.1','localhost','[::1]'].includes(base.hostname)||base.username||base.password||base.href!==base.origin+'/')throw new Error('Demo credentials may only be sent to a loopback origin.');
async function request(path,body,token=process.env.INGESTION_ADMIN_TOKEN){
 const response=await fetch(new URL(path,base),{method:body?'POST':'GET',redirect:'error',headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 const value=await response.json();if(!response.ok)throw new Error(`Demo request failed: ${value.error?.code??response.status}`);return value;
}
const current=await request('/v1/simulation');
let state=await request('/v1/simulation/start',{scenario:'civilian-relief',inputMode:'gateway',commandId:randomUUID(),...(configuration?{configuration}:{}),...(current.status==='ready'?{replaceRunId:current.world.runId}:{})});
const sources=JSON.parse(process.env.INGESTION_SOURCES_JSON),sequence=new Map();
const print=phase=>console.log(JSON.stringify({phase,fictional:true,revision:state.world.revision,servedPriority:state.plan.objective.servedPriority,assignments:state.plan.assignments.length,verified:state.validation.valid,namespace:state.inputs.namespace}));
print('initial');
async function send(type,id,data,phase){
 const source=sources.find(s=>s.sourceId===state.inputs.authorities[type]);if(!source)throw new Error('Designated source credentials are missing.');
 const key=type+id,n=(sequence.get(key)??0)+1;sequence.set(key,n);
 const now=Date.now();await request('/v1/events',{schemaVersion:1,eventId:randomUUID(),sourceId:source.sourceId,type,entityId:state.inputs.namespace+id,sequence:n,observedAt:new Date(now).toISOString(),validUntil:new Date(now+60000).toISOString(),data},source.token);
 state=await request('/v1/simulation');print(phase);await delay(1200);
}
const target=state.world.requests[0]?.destinationId??state.world.weather[0]?.airportId;
if(target){
 await send('weather.observation',target,{temperatureC:24,windSpeedMps:25,visibilityM:1500,condition:'storm'},'numeric-weather-disruption');
 await send('weather.observation',target,{temperatureC:24,windSpeedMps:5,visibilityM:10000,condition:'clear'},'weather-restored');
}
const aircraft=state.world.aircraft[0];if(aircraft)await send('aircraft.status',aircraft.id,{status:'maintenance',airportId:state.inputs.namespace+aircraft.airportId,capacityKg:aircraft.capacityKg},'aircraft-maintenance');
const airport=state.world.airports.find(a=>a.id===target);if(airport){
 const previous={status:airport.status,arrivalsPerHour:airport.arrivalsPerSlot*2,departuresPerHour:airport.departuresPerSlot*2};
 await send('airport.capacity',airport.id,{status:'closed',arrivalsPerHour:0,departuresPerHour:0},'airport-closure');
 await send('airport.capacity',airport.id,previous,'airport-restored');
}
const cargo=state.world.requests[0];if(cargo)await send('cargo.request',cargo.id,{category:cargo.category,massKg:Math.max(1,Math.floor(cargo.massKg/2)),originAirportId:state.inputs.namespace+cargo.originId,destinationAirportId:state.inputs.namespace+cargo.destinationId,requestedDeliveryBy:new Date(Date.parse(state.world.createdAt)+cargo.deadlineSlot*30*60000).toISOString(),temperatureControlled:cargo.temperatureControlled},'cargo-demand-change');
const crew=state.world.crews.find(c=>c.status!=='available');if(crew)await send('crew.availability',crew.id,{status:'available',qualifications:crew.qualifications,availableFrom:new Date(Date.parse(state.world.createdAt)+crew.fromSlot*30*60000).toISOString(),availableUntil:new Date(Date.parse(state.world.createdAt)+crew.toSlot*30*60000).toISOString()},'crew-availability');
if(liveWeather&&state.world.airports.length){
 const airportId=state.world.airports.find(a=>a.id!==target)?.id??state.world.airports[0].id;
 state=await request('/v1/simulation/weather',{commandId:randomUUID(),runId:state.world.runId,expectedRevision:state.world.revision,airportId,location:'delhi'});
 console.log(JSON.stringify({weatherFeed:state.weatherFeed}));print('public-weather');
}
console.log('Open /monitor/ with the separate viewer token. Bound source readings expire after60seconds; the timer recomputes a verified proposal. Nothing is dispatched.');
