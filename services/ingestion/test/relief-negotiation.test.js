import test from 'node:test';
import assert from 'node:assert/strict';
import { createReliefWorld, advanceReliefWorld, RELIEF_PHASES } from '../src/relief-world.js';
import { optimizeReliefWorld, validateReliefPlan, validateReliefAssignmentSeed } from '../src/relief-planner.js';
import { runReliefNegotiation, finishReliefNegotiation, negotiationSettingsSchema, validateReliefNegotiationReport } from '../src/relief-negotiation.js';
const agents = ['fleet','crew','weather','airport','cargo'];
function world() { return createReliefWorld({runId:'00000000-0000-4000-8000-000000000001',now:0}); }

test('peers execute proposals, objections, bids and counterproposals before unanimous commitment',()=>{
 const w=world(), original=structuredClone(w), n=runReliefNegotiation(w);
 assert.equal(n.mode,'deterministic-autonomous');assert.equal(n.topology,'fully-connected-peers');
 for(const kind of ['cfp','proposal','reject','bid','counterproposal','accept','commit'])assert.ok(n.messages.some(m=>m.kind===kind),kind);
 assert.equal(n.assignments.length,2);assert.equal(validateReliefAssignmentSeed(w,n.assignments).valid,true);
 for(const commit of n.messages.filter(m=>m.kind==='commit'&&m.to==='cargo')) {
  const votes=n.messages.filter(m=>m.kind==='accept'&&m.proposalId===commit.proposalId&&m.to==='supervisor');
  assert.deepEqual(votes.map(m=>m.from).sort(),[...agents].sort());
 }
 for(const from of agents)for(const to of agents.filter(a=>a!==from))assert.ok(n.messages.some(m=>m.from===from&&m.to===to),`${from}->${to}`);
 assert.deepEqual(w,original);assert.deepEqual(runReliefNegotiation(w),n);
});
test('round and message budgets never create consensus from missing votes',()=>{
 for(const settings of [{maxRounds:1},{maxMessages:32},{maxMessages:40},{maxMessages:80}]) {
  const w=world(), n=runReliefNegotiation(w,{settings});
  assert.ok(n.messages.length<=n.settings.maxMessages);assert.ok(n.requests.every(r=>r.rounds<=n.settings.maxRounds));
  assert.equal(validateReliefAssignmentSeed(w,n.assignments).valid,true);
  if(settings.maxMessages===32){assert.equal(n.status,'budget_exhausted');assert.equal(n.assignments.length,0);}
 }
});
test('seeded exact optimization retains canonical optimum and reports negotiated-vs-final outcome',()=>{
 let w=world(), previous=[];
 for(const phase of [null,...RELIEF_PHASES]) {
  if(phase)w=advanceReliefWorld(w,phase);
  const n=runReliefNegotiation(w,{previousAssignments:previous});
  assert.equal(validateReliefAssignmentSeed(w,n.assignments,{previousAssignments:previous}).valid,true);
  const p=optimizeReliefWorld(w,{previousAssignments:previous,initialAssignments:n.assignments});
  assert.deepEqual(p.assignments,optimizeReliefWorld(w,{previousAssignments:previous}).assignments);
  const v=validateReliefPlan(w,p,{previousAssignments:previous});
  const complete=finishReliefNegotiation(n,w,p,v,{previousAssignments:previous});
  assert.equal(complete.outcome.verified,true);assert.ok(complete.outcome.finalServedPriority>=complete.outcome.seedServedPriority);
  assert.ok(complete.messages.length<=complete.settings.maxMessages);previous=p.assignments;
 }
});
test('capacity contention triggers a slot counterproposal and infeasible worlds produce no agreement',()=>{
 const w=world();w.airports.find(a=>a.id==='SIM-HUB').departuresPerSlot=1;
 const n=runReliefNegotiation(w);assert.ok(n.messages.some(m=>m.ruleCodes.includes('DEPARTURE_CAPACITY_EXCEEDED')));
 assert.equal(validateReliefAssignmentSeed(w,n.assignments).valid,true);assert.equal(new Set(n.assignments.map(a=>a.departureSlot)).size,n.assignments.length);
 w.crews.forEach(c=>{c.status='rest';});const empty=runReliefNegotiation(w);assert.equal(empty.status,'no_agreement');assert.deepEqual(empty.assignments,[]);
});
test('settings strictness, disabled mode and revision identity prevent invented consensus',()=>{
 for(const bad of [{maxRounds:0},{maxRounds:9},{maxMessages:513},{enabled:'true'},{tools:[]}])assert.equal(negotiationSettingsSchema.safeParse(bad).success,false);
 const w=world(), n=runReliefNegotiation(w,{settings:{enabled:false}}), p=optimizeReliefWorld(w),v=validateReliefPlan(w,p);
 assert.equal(n.status,'disabled');assert.deepEqual(n.messages,[]);assert.equal(finishReliefNegotiation(n,w,p,v).outcome.status,'disabled');
 assert.throws(()=>finishReliefNegotiation({...n,revision:1},w,p,v));
 assert.throws(()=>finishReliefNegotiation(n,w,p,{valid:false,errors:['bad']}));
});

test('audit rejects fabricated agreement, metadata, missing peer deliveries and missing counterbid causality',()=>{
 const w=world(), valid=runReliefNegotiation(w);
 const resequence=n=>n.messages.forEach((m,i)=>{m.id=`SIM-NEG-${w.runId}-${w.revision}-${i+1}`;});
 for(const corrupt of [
  n=>Object.assign(n,{status:'agreed',messages:[],assignments:[],requests:[],agentStates:[]}),
  n=>{n.roundsCompleted=-99;},
  n=>{n.messages[0].entityIds=['SIM-NOT-IN-WORLD'];},
  n=>{n.messages=n.messages.filter(m=>!(['accept','reject'].includes(m.kind)&&m.to!=='supervisor'));resequence(n);},
  n=>{n.messages=n.messages.filter(m=>!['bid','counterproposal'].includes(m.kind));resequence(n);},
 ]) {
  const n=structuredClone(valid);corrupt(n);assert.equal(validateReliefNegotiationReport(w,n).valid,false);
 }
});
test('audit binds failure metadata to trusted prior context and resolution can use self-contained context',()=>{
 const w=world(), n=runReliefNegotiation(w), p=optimizeReliefWorld(w,{initialAssignments:n.assignments});
 const prior=p.assignments, next=runReliefNegotiation(w,{previousAssignments:prior});
 const final=optimizeReliefWorld(w,{previousAssignments:prior,initialAssignments:next.assignments});
 assert.equal(finishReliefNegotiation(next,w,final,validateReliefPlan(w,final,{previousAssignments:prior})).outcome.verified,true);
 const failed={...n,status:'failed',errorCode:'NEGOTIATION_FAILED',roundsCompleted:0,requests:[],agentStates:[],messages:[],assignments:[],previousAssignments:['not a tuple']};
 assert.equal(validateReliefNegotiationReport(w,failed,{previousAssignments:[]}).valid,false);
});
