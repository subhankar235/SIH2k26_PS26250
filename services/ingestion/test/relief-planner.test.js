import assert from 'node:assert/strict';
import test from 'node:test';
import { optimizeReliefWorld, validateReliefPlan } from '../src/planning/planner.js';
import { createReliefWorld, advanceReliefWorld, RELIEF_PHASES } from '../src/planning/world.js';

function world() {
  return {
    version: 1, simulation: true, runId: '00000000-0000-4000-8000-000000000001', revision: 0, tick: 0,
    policy: { slots: [0, 1, 2], slotMinutes: 30, minVisibilityM: 3000, maxWindSpeedMps: 15 },
    aircraft: [1, 2].map(n => ({ id: `SIM-A${n}`, airportId: 'SIM-O', capacityKg: 100, coldStorage: n === 1, status: 'available', validThroughTick: 10 })),
    crews: [1, 2].map(n => ({ id: `SIM-C${n}`, status: 'available', qualifications: ['relief-pilot'], fromSlot: 0, toSlot: 4, validThroughTick: 10 })),
    airports: ['SIM-O', 'SIM-D'].map(id => ({ id, status: 'open', arrivalsPerSlot: 1, departuresPerSlot: 1, validThroughTick: 10 })),
    weather: ['SIM-O', 'SIM-D'].map(airportId => ({ airportId, windSpeedMps: 5, visibilityM: 5000, condition: 'clear', validThroughTick: 10 })),
    routes: [{ originId: 'SIM-O', destinationId: 'SIM-D', durationSlots: 1 }],
    requests: [
      { id: 'SIM-R1', category: 'medical', massKg: 80, originId: 'SIM-O', destinationId: 'SIM-D', temperatureControlled: true, priority: 5, deadlineSlot: 1, validThroughTick: 10 },
      { id: 'SIM-R2', category: 'food', massKg: 50, originId: 'SIM-O', destinationId: 'SIM-D', temperatureControlled: false, priority: 3, deadlineSlot: 3, validThroughTick: 10 },
      { id: 'SIM-R3', category: 'water', massKg: 40, originId: 'SIM-O', destinationId: 'SIM-D', temperatureControlled: false, priority: 1, deadlineSlot: 3, validThroughTick: 10 },
    ], demandHistory: [{ day: 0, demand: 100 }],
  };
}

test('known optimum respects cold storage, one delivery per resource and airport slot capacity', () => {
  const w = world();
  const result = optimizeReliefWorld(w);
  assert.equal(result.status, 'optimal');
  assert.deepEqual(result.objective, { servedPriority: 8, changedAssignments: 0, totalArrivalSlots: 3 });
  assert.deepEqual(result.assignments, [
    { requestId: 'SIM-R1', aircraftId: 'SIM-A1', crewId: 'SIM-C1', departureSlot: 0, arrivalSlot: 1 },
    { requestId: 'SIM-R2', aircraftId: 'SIM-A2', crewId: 'SIM-C2', departureSlot: 1, arrivalSlot: 2 },
  ]);
  assert.deepEqual(result.agentReports.map(r => r.agentId), ['fleet', 'crew', 'weather', 'airport', 'cargo']);
  assert.deepEqual(validateReliefPlan(w, result), { valid: true, errors: [] });
  assert.deepEqual(optimizeReliefWorld(w), result);
});

test('priority outranks preserving previous assignments and preservation outranks arrival time', () => {
  const w = world();
  const previousAssignments = [
    { requestId: 'SIM-R1', aircraftId: 'SIM-A1', crewId: 'SIM-C2', departureSlot: 0, arrivalSlot: 1 },
    { requestId: 'SIM-R2', aircraftId: 'SIM-A2', crewId: 'SIM-C1', departureSlot: 2, arrivalSlot: 3 },
  ];
  const p = optimizeReliefWorld(w, { previousAssignments });
  assert.deepEqual(p.assignments, previousAssignments);
  assert.deepEqual(p.objective, { servedPriority: 8, changedAssignments: 0, totalArrivalSlots: 4 });
  assert.equal(validateReliefPlan(w, p, { previousAssignments }).valid, true);
  const inferiorPrevious = [{ ...previousAssignments[1], requestId: 'SIM-R3' }];
  const changed = optimizeReliefWorld(w, { previousAssignments: inferiorPrevious });
  assert.equal(changed.objective.servedPriority, 8);
  assert.equal(changed.objective.changedAssignments, 1);
  const removedPrevious = [{ ...previousAssignments[0], requestId: 'SIM-REMOVED' }];
  assert.equal(optimizeReliefWorld(w, { previousAssignments: removedPrevious }).objective.changedAssignments, 0);
});

test('node exhaustion is bounded and returns a checked feasible result without claiming optimality', () => {
  const w = world();
  const p = optimizeReliefWorld(w, { nodeLimit: 1 });
  assert.equal(p.status, 'feasible_budget');
  assert.equal(p.diagnostics.nodesExplored, 1);
  assert.equal(p.diagnostics.budgetExhausted, true);
  assert.equal(validateReliefPlan(w, p).valid, true);
  assert.equal(p.unserved.length, 3);
});

test('blocked and expired evidence produces an explanatory empty plan', () => {
  const w = world();
  w.tick = 2;
  w.weather[0].validThroughTick = 1;
  w.airports[1].status = 'closed';
  const p = optimizeReliefWorld(w);
  assert.equal(p.status, 'optimal');
  assert.equal(p.assignments.length, 0);
  assert.equal(p.unserved.length, 3);
  assert.ok(p.unserved.every(r => r.reasonCodes.includes('WEATHER_EXPIRED') && r.reasonCodes.includes('AIRPORT_CLOSED')));
  assert.equal(validateReliefPlan(w, p).valid, true);
  assert.ok(p.agentReports.find(r => r.agentId === 'weather').findings.some(f => f.code === 'WEATHER_EXPIRED'));
});

test('reordering world entities does not change deterministic output', () => {
  const w = world();
  const p = optimizeReliefWorld(w);
  for (const k of ['aircraft', 'crews', 'airports', 'weather', 'routes', 'requests']) w[k].reverse();
  assert.deepEqual(optimizeReliefWorld(w), p);
});

test('independent checker rejects tampered IDs, duplicates, timings, objectives and report eligibility', () => {
  const w = world();
  const p = optimizeReliefWorld(w);
  const mutations = [
    q => { q.assignments[0].aircraftId = 'SIM-INVENTED'; },
    q => { q.assignments[1].aircraftId = q.assignments[0].aircraftId; },
    q => { q.assignments[1].crewId = q.assignments[0].crewId; },
    q => { q.assignments[1].requestId = q.assignments[0].requestId; },
    q => { q.assignments[0].departureSlot = 9; },
    q => { q.assignments[0].arrivalSlot = 2; },
    q => { q.objective.servedPriority = 99; },
    q => { q.objective.changedAssignments = 99; },
    q => { q.objective.totalArrivalSlots = 99; },
    q => { q.agentReports[0].eligibleIds.push('SIM-INVENTED'); },
    q => { q.agentReports[0].findings[0].message = 'invented evidence'; },
    q => { q.unserved = []; },
  ];
  for (const mutate of mutations) {
    const q = structuredClone(p); mutate(q);
    assert.equal(validateReliefPlan(w, q).valid, false);
  }
});

test('checker independently rejects every hard constraint when world evidence changes', () => {
  const p = optimizeReliefWorld(world());
  const mutations = [
    w => { w.aircraft[0].capacityKg = 10; },
    w => { w.aircraft[0].coldStorage = false; },
    w => { w.aircraft[0].airportId = 'SIM-D'; },
    w => { w.aircraft[0].status = 'maintenance'; },
    w => { w.aircraft[0].validThroughTick = 0; w.tick = 1; },
    w => { w.crews[0].status = 'rest'; },
    w => { w.crews[0].qualifications = []; },
    w => { w.crews[0].fromSlot = 1; },
    w => { w.crews[0].toSlot = 0; },
    w => { w.crews[0].validThroughTick = 0; w.tick = 1; },
    w => { w.requests[0].deadlineSlot = 0; },
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
  ];
  for (const mutate of mutations) {
    const w = world(); mutate(w);
    assert.equal(validateReliefPlan(w, p).valid, false);
  }
});

test('optimizer fails closed on malformed or oversized toy worlds and invalid budgets', () => {
  for (const mutate of [
    w => { w.aircraft.push(...w.aircraft); },
    w => { w.requests[0].id = 'REAL-R1'; },
    w => { w.aircraft[0].capacityKg = Infinity; },
    w => { w.routes[0].durationSlots = 2; },
    w => { w.policy.slots.push(3); },
    w => { w.requests[0].category = 'weapons'; },
    w => { w.simulation = false; },
  ]) {
    const w = world(); mutate(w);
    assert.throws(() => optimizeReliefWorld(w), /world/i);
    assert.equal(validateReliefPlan(w, {}).valid, false);
  }
  for (const nodeLimit of [0, -1, Infinity, 100001, 1.5]) assert.throws(() => optimizeReliefWorld(world(), { nodeLimit }), /nodeLimit/);
});

test('the canonical fictional story replans every phase and expiry removes all deliveries', () => {
  let w = createReliefWorld({ runId: '00000000-0000-4000-8000-000000000001', now: 0 });
  let previousAssignments = [];
  for (const [i, expectedPriority] of [9, 7, 7, 0, 10, 0].entries()) {
    if (i) w = advanceReliefWorld(w, RELIEF_PHASES[i - 1]);
    const p = optimizeReliefWorld(w, { previousAssignments });
    assert.equal(p.status, 'optimal');
    assert.equal(p.objective.servedPriority, expectedPriority);
    assert.deepEqual(validateReliefPlan(w, p, { previousAssignments }), { valid: true, errors: [] });
    previousAssignments = p.assignments;
  }
});

test('constraints are checked independently even when specialist reports are refreshed', () => {
  const w = world();
  const p = optimizeReliefWorld(w);
  w.aircraft[0].capacityKg = 10;
  p.agentReports = optimizeReliefWorld(w).agentReports;
  const checked = validateReliefPlan(w, p);
  assert.equal(checked.valid, false);
  assert.ok(checked.errors.includes('Payload capacity exceeded'));
  assert.ok(!checked.errors.includes('Specialist evidence mismatch'));
});

test('checker rejects fabricated unserved reasons and search diagnostics', () => {
  const w = world();
  const p = optimizeReliefWorld(w);
  p.unserved[0].reasonCodes = ['ALIEN_INTERVENTION'];
  assert.equal(validateReliefPlan(w, p).valid, false);
  const q = optimizeReliefWorld(w);
  q.diagnostics.candidateCount = 999;
  assert.equal(validateReliefPlan(w, q).valid, false);
});

// An intentionally separate exhaustive oracle for this tiny fixture. It forms
// whole products, then filters constraints, rather than using planner reports
// or the planner's recursive resource bookkeeping.
function oracle(w, previousAssignments) {
  const choices = w.requests.map(r => [null, ...w.aircraft.flatMap(a => w.crews.flatMap(c => [0, 1, 2].map(departureSlot => ({
    requestId: r.id, aircraftId: a.id, crewId: c.id, departureSlot, arrivalSlot: departureSlot + 1,
  }))))]);
  let products = [[]];
  for (const row of choices) products = products.flatMap(prefix => row.map(choice => [...prefix, choice]));
  let best;
  for (const product of products) {
    const assignments = product.filter(Boolean);
    if (new Set(assignments.map(a => a.aircraftId)).size !== assignments.length || new Set(assignments.map(a => a.crewId)).size !== assignments.length) continue;
    if (assignments.some(a => {
      const r = w.requests.find(r => r.id === a.requestId), aircraft = w.aircraft.find(v => v.id === a.aircraftId);
      return aircraft.capacityKg < r.massKg || (r.temperatureControlled && !aircraft.coldStorage) || a.arrivalSlot > r.deadlineSlot;
    })) continue;
    if ([0, 1, 2].some(s => assignments.filter(a => a.departureSlot === s).length > w.airports[0].departuresPerSlot) ||
        [1, 2, 3].some(s => assignments.filter(a => a.arrivalSlot === s).length > w.airports[1].arrivalsPerSlot)) continue;
    const priority = assignments.reduce((sum, a) => sum + w.requests.find(r => r.id === a.requestId).priority, 0);
    const changed = previousAssignments.filter(prior => !assignments.some(a => Object.keys(prior).every(k => prior[k] === a[k]))).length;
    const arrivals = assignments.reduce((sum, a) => sum + a.arrivalSlot, 0);
    const score = [-priority, changed, arrivals];
    if (!best || score.some((value, i) => value < best[i] && score.slice(0, i).every((n, j) => n === best[j]))) best = score;
  }
  return { servedPriority: -best[0], changedAssignments: best[1], totalArrivalSlots: best[2] };
}

test('exact objective matches an independent exhaustive oracle across small variants', () => {
  for (let variation = 0; variation < 8; variation++) {
    const w = world();
    w.requests.forEach((r, i) => { r.priority = 1 + (variation + i * 2) % 5; r.deadlineSlot = 1 + (variation + i) % 3; });
    w.aircraft[1].coldStorage = variation % 2 === 0;
    w.airports[0].departuresPerSlot = 1 + variation % 2;
    const previousAssignments = variation % 3 ? [] : [{ requestId: 'SIM-R2', aircraftId: 'SIM-A2', crewId: 'SIM-C2', departureSlot: 2, arrivalSlot: 3 }];
    const p = optimizeReliefWorld(w, { previousAssignments });
    assert.equal(p.status, 'optimal');
    assert.deepEqual(p.objective, oracle(w, previousAssignments));
  }
});
