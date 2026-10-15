import { reliefEvents } from './world.js';
import { validateEvent } from '../contracts/events.js';
import { ApiError } from '../platform/errors.js';

const collections = {'aircraft.status':'aircraft','crew.availability':'crews','weather.observation':'weather','airport.capacity':'airports','cargo.request':'requests'};
export function boundEntity(snapshot,event) {
  const input=snapshot.inputs;
  if(snapshot.status!=='ready'||input?.mode!=='gateway'||input.authorities[event.type]!==event.sourceId||!event.entityId.startsWith(input.namespace)) return null;
  const id=event.entityId.slice(input.namespace.length);
  return snapshot.world[collections[event.type]??'aircraft'].find(e=>(event.type==='weather.observation'?e.airportId:e.id)===id)??null;
}
function invalid() {throw new ApiError(422,'SIMULATION_INPUT_INCOMPATIBLE','Bound observation is incompatible with the bounded fictional scenario.');}
function slot(world,time,min,max) {
  const n=(Date.parse(time)-Date.parse(world.createdAt))/(30*60000);
  if(!Number.isInteger(n)||n<min||n>max) invalid();
  return n;
}
function airport(snapshot,id) {
 if(!id.startsWith(snapshot.inputs.namespace)) invalid();
 const local=id.slice(snapshot.inputs.namespace.length);
 if(!snapshot.world.airports.some(a=>a.id===local)) invalid();
 return local;
}
/** Apply ordinary source facts; preserve scenario-only priority/cold-storage metadata. */
export function applyBoundObservation(snapshot,event,now) {
 const target=boundEntity(snapshot,event);if(!target)return false;
 const d=event.data,w=snapshot.world;
 if(event.type==='aircraft.status') {
   Object.assign(target,{status:d.status,airportId:airport(snapshot,d.airportId),capacityKg:d.capacityKg});
   if(d.maintenanceDueAt&&Date.parse(d.maintenanceDueAt)<=now)target.status='maintenance';
 } else if(event.type==='crew.availability') {
   if(d.qualifications.length>8||d.qualifications.some(q=>!/^[a-z][a-z-]{0,63}$/.test(q)))invalid();
   Object.assign(target,{status:d.status,qualifications:d.qualifications,fromSlot:slot(w,d.availableFrom,0,4),toSlot:slot(w,d.availableUntil,0,4)});
 } else if(event.type==='weather.observation') Object.assign(target,{temperatureC:d.temperatureC,windSpeedMps:d.windSpeedMps,visibilityM:d.visibilityM,condition:d.condition});
 else if(event.type==='airport.capacity') {
   if([d.arrivalsPerHour,d.departuresPerHour].some(n=>n>6||n%2!==0))invalid();
   Object.assign(target,{status:d.status,arrivalsPerSlot:d.arrivalsPerHour/2,departuresPerSlot:d.departuresPerHour/2});
 } else if(event.type==='cargo.request') {
   const originId=airport(snapshot,d.originAirportId),destinationId=airport(snapshot,d.destinationAirportId);
   if(!w.routes.some(r=>r.originId===originId&&r.destinationId===destinationId))invalid();
   Object.assign(target,{category:d.category,massKg:d.massKg,originId,destinationId,temperatureControlled:d.temperatureControlled,deadlineSlot:slot(w,d.requestedDeliveryBy,1,4)});
 }
 target.validThroughTick=10;
 const binding={type:event.type,entityId:event.entityId,scenarioEntityId:event.entityId.slice(snapshot.inputs.namespace.length),eventId:event.eventId,sourceId:event.sourceId,observedAt:event.observedAt,validUntil:event.validUntil,expired:false};
 if(event.type==='aircraft.status'&&d.maintenanceDueAt) {
   binding.maintenanceDueAt=d.maintenanceDueAt;
   if(target.status==='available')binding.validUntil=new Date(Math.min(Date.parse(event.validUntil),Date.parse(d.maintenanceDueAt))).toISOString();
 }
 const i=snapshot.inputs.bindings.findIndex(b=>b.type===event.type&&b.entityId===event.entityId);
 if(i<0)snapshot.inputs.bindings.push(binding);else snapshot.inputs.bindings[i]=binding;
 return true;
}
export function expireBoundObservations(snapshot,now) {
 const due=snapshot.inputs?.bindings.filter(b=>!b.expired&&Date.parse(b.validUntil)<=now)??[];
 if(!due.length)return false;
 // Last reserved revision ends all bound resource validity rather than keeping stale input usable.
 const expired=snapshot.world.revision>=19?snapshot.inputs.bindings.filter(b=>!b.expired):due;
 snapshot.world.tick=Math.max(1,snapshot.world.tick);
 for(const b of expired){
   const target=boundEntity(snapshot,{...b,sourceId:b.sourceId});
   if(target)target.validThroughTick=0;
   b.expired=true;b.expiryReason=Date.parse(b.validUntil)<=now?'ttl':'revision-capacity';
 }
 return true;
}

/** Mirrors inherit bound input freshness; expired facts are never refreshed by replanning. */
export function mirroredReliefEvents(world,sources,inputs,now) {
  const prefix=`relief-${world.runId}-`;
  return reliefEvents(world,sources,now).flatMap(event=>{
    const id=event.entityId.slice(prefix.length);
    const binding=inputs?.mode==='gateway'?inputs.bindings.find(b=>b.type===event.type&&b.scenarioEntityId===id):null;
    if(!binding)return [event];
    if(binding.expired||Date.parse(binding.validUntil)<=now)return [];
    event.validUntil=new Date(Math.min(Date.parse(event.validUntil),Date.parse(binding.validUntil))).toISOString();
    if(event.type==='aircraft.status'&&binding.maintenanceDueAt)event.data.maintenanceDueAt=binding.maintenanceDueAt;
    return [validateEvent(event,{now})];
  });
}
