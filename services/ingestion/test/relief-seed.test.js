import assert from 'node:assert/strict';
import test from 'node:test';
import { getReliefNegotiationContext, optimizeReliefWorld, validateReliefAssignmentSeed, validateReliefPlan } from '../src/relief-planner.js';
import { createReliefWorld, advanceReliefWorld, RELIEF_PHASES } from '../src/relief-world.js';

const world = () => createReliefWorld({ runId: '00000000-0000-4000-8000-000000000001', now: 0 });
const assignment = (overrides = {}) => ({ requestId: 'SIM-REQ-MED', aircraftId: 'SIM-A1', crewId: 'SIM-C1', departureSlot: 0, arrivalSlot: 1, ...overrides });

test('negotiation context exposes the stable raw tuple universe, feasible subset and canonical reports', () => {
  const w = world(), before = structuredClone(w);
  const context = getReliefNegotiationContext(w);
  assert.equal(context.candidates.length, 108);
  assert.equal(new Set(context.candidates.map(c => c.id)).size, 108);
  assert.deepEqual(context.agentReports, optimizeReliefWorld(w).agentReports);
  const feasible = new Set(context.feasibleCandidateIds);
  assert.ok(feasible.size > 0 && feasible.size < context.candidates.length);
  for (const candidate of context.candidates) {
    const a = candidate.assignment;
    assert.equal(candidate.id, `SIM-CAND-${a.requestId.slice(4)}~${a.aircraftId.slice(4)}~${a.crewId.slice(4)}~${a.departureSlot}~${a.arrivalSlot}`);
    assert.equal(feasible.has(candidate.id), validateReliefAssignmentSeed(w, [a]).valid);
  }
  assert.deepEqual(w, before);
  for (const key of ['requests', 'aircraft', 'crews', 'weather', 'airports', 'routes']) w[key].reverse();
  assert.deepEqual(getReliefNegotiationContext(w), context);
  const reordered = structuredClone(w);
  context.candidates[0].assignment.aircraftId = 'SIM-TAMPERED';
  context.agentReports[0].eligibleIds.length = 0;
  assert.deepEqual(w, reordered);
  assert.ok(!getReliefNegotiationContext(w).candidates.some(c => c.assignment.aircraftId === 'SIM-TAMPERED'));
});

test('all story phases expose bounded contexts and accept their independently checked plans as seeds', () => {
  let w = world(), previousAssignments = [];
  for (let phase = 0; phase <= RELIEF_PHASES.length; phase++) {
    if (phase) w = advanceReliefWorld(w, RELIEF_PHASES[phase - 1]);
    const context = getReliefNegotiationContext(w);
    assert.ok(context.candidates.length <= 135);
    const plan = optimizeReliefWorld(w, { previousAssignments });
    assert.deepEqual(validateReliefAssignmentSeed(w, plan.assignments, { previousAssignments }), { valid: true, errors: [] });
    for (const c of context.candidates) assert.equal(context.feasibleCandidateIds.includes(c.id), validateReliefAssignmentSeed(w, [c.assignment]).valid);
    if (phase === RELIEF_PHASES.length) {
      assert.equal(context.feasibleCandidateIds.length, 0);
      assert.ok(context.candidates.length > 0);
      assert.equal(validateReliefAssignmentSeed(w, [assignment()]).valid, false);
    }
    previousAssignments = plan.assignments;
  }
});

test('seed checker rejects malformed tuples, unknown entities, duplicates and forged extra fields', () => {
  const w = world();
  for (const seed of [null, {}, [null], [assignment({ aircraftId: 'SIM-INVENTED' })], [assignment({ requestId: 'REAL-R' })],
    [assignment({ departureSlot: 3 })], [assignment({ arrivalSlot: 2 })], [assignment({ extra: true })],
    [assignment(), assignment()], Array.from({ length: 6 }, () => assignment()),
    [assignment(), assignment({ requestId: 'SIM-REQ-FOOD', crewId: 'SIM-C2' })],
    [assignment(), assignment({ requestId: 'SIM-REQ-FOOD', aircraftId: 'SIM-A3' })]]) {
    assert.equal(validateReliefAssignmentSeed(w, seed).valid, false, JSON.stringify(seed));
    assert.throws(() => optimizeReliefWorld(w, { initialAssignments: seed }), /initialAssignments/);
  }
  assert.equal(validateReliefAssignmentSeed(w, [], { previousAssignments: [null] }).valid, false);
  assert.equal(validateReliefAssignmentSeed({ ...w, simulation: false }, []).valid, false);
  assert.throws(() => getReliefNegotiationContext({ ...w, simulation: false }), /world/);
});

test('seed checker independently enforces resource, duty, cargo, weather, airport and expiry rules', () => {
  const mutations = [
    w => { w.aircraft[0].capacityKg = 100; },
    w => { w.aircraft[0].coldStorage = false; },
    w => { w.aircraft[0].airportId = 'SIM-CLINIC'; },
    w => { w.aircraft[0].status = 'maintenance'; },
    w => { w.aircraft[0].validThroughTick = 0; w.tick = 1; },
    w => { w.crews[0].status = 'rest'; },
    w => { w.crews[0].qualifications = []; },
    w => { w.crews[0].fromSlot = 1; },
    w => { w.crews[0].toSlot = 0; },
    w => { w.crews[0].validThroughTick = 0; w.tick = 1; },
    w => { w.requests[0].validThroughTick = 0; w.tick = 1; },
    w => { w.routes = []; },
    w => { w.weather = []; },
    w => { w.weather[0].windSpeedMps = 16; },
    w => { w.weather[1].visibilityM = 2999; },
    w => { w.weather[1].validThroughTick = 0; w.tick = 1; },
    w => { w.airports[0].status = 'closed'; },
    w => { w.airports[1].arrivalsPerSlot = 0; },
    w => { w.airports[0].departuresPerSlot = 0; },
    w => { w.airports[0].validThroughTick = 0; w.tick = 1; },
    w => { w.airports = w.airports.filter(a => a.id !== 'SIM-CLINIC'); },
  ];
  for (const mutate of mutations) {
    const w = world(); mutate(w);
    const checked = validateReliefAssignmentSeed(w, [assignment()]);
    assert.equal(checked.valid, false, mutate.toString());
    assert.ok(checked.errors.length > 0);
  }
  const w = world(); w.requests[0].deadlineSlot = 1;
  assert.equal(validateReliefAssignmentSeed(w, [assignment({ departureSlot: 1, arrivalSlot: 2 })]).valid, false);
  const seed = [assignment(), assignment({ requestId: 'SIM-REQ-FOOD', aircraftId: 'SIM-A3', crewId: 'SIM-C2' })];
  assert.equal(validateReliefAssignmentSeed(w, seed).valid, true);
  w.airports[0].departuresPerSlot = 1;
  assert.ok(validateReliefAssignmentSeed(w, seed).errors.includes('Airport departure capacity exceeded'));
  w.airports[0].departuresPerSlot = 2; w.airports[1].arrivalsPerSlot = 1;
  w.requests.find(r => r.id === 'SIM-REQ-FOOD').destinationId = 'SIM-CLINIC';
  assert.ok(validateReliefAssignmentSeed(w, seed).errors.includes('Airport arrival capacity exceeded'));
});

test('budget-one search retains a valid seed with honest unchanged diagnostics and immutable inputs', () => {
  const w = world(), initialAssignments = [assignment()], previousAssignments = [assignment()];
  const before = structuredClone({ w, initialAssignments, previousAssignments });
  const empty = optimizeReliefWorld(w, { nodeLimit: 1 });
  const seeded = optimizeReliefWorld(w, { nodeLimit: 1, initialAssignments, previousAssignments });
  assert.equal(empty.objective.servedPriority, 0);
  assert.deepEqual(seeded.assignments, initialAssignments);
  assert.deepEqual(seeded.objective, { servedPriority: 5, changedAssignments: 0, totalArrivalSlots: 1 });
  assert.equal(seeded.status, 'feasible_budget');
  assert.equal(seeded.diagnostics.nodesExplored, 1);
  assert.equal(seeded.diagnostics.nodeLimit, 1);
  assert.equal(seeded.diagnostics.budgetExhausted, true);
  assert.deepEqual(Object.keys(seeded.diagnostics), Object.keys(empty.diagnostics));
  assert.deepEqual(validateReliefPlan(w, seeded, { previousAssignments }), { valid: true, errors: [] });
  assert.deepEqual({ w, initialAssignments, previousAssignments }, before);
  seeded.assignments[0].aircraftId = 'SIM-TAMPERED';
  assert.deepEqual({ w, initialAssignments, previousAssignments }, before);
  for (const nodeLimit of [0, -1, 1.5, 100001, Infinity]) assert.throws(() => optimizeReliefWorld(w, { initialAssignments, nodeLimit }), /nodeLimit/);
});

test('completed seeded search preserves optimum, prior-assignment preference, arrivals and canonical ties', () => {
  const w = world();
  for (const previousAssignments of [[], [assignment({ crewId: 'SIM-C2', departureSlot: 1, arrivalSlot: 2 })]]) {
    const unseeded = optimizeReliefWorld(w, { previousAssignments });
    for (const initialAssignments of [[], [assignment()], [assignment({ aircraftId: 'SIM-A3', crewId: 'SIM-C2', departureSlot: 1, arrivalSlot: 2 })], unseeded.assignments]) {
      const seeded = optimizeReliefWorld(w, { previousAssignments, initialAssignments });
      assert.equal(seeded.status, 'optimal');
      assert.deepEqual(seeded.assignments, unseeded.assignments);
      assert.deepEqual(seeded.objective, unseeded.objective);
      assert.deepEqual(seeded.agentReports, unseeded.agentReports);
      assert.deepEqual(validateReliefPlan(w, seeded, { previousAssignments }), { valid: true, errors: [] });
    }
  }
});
