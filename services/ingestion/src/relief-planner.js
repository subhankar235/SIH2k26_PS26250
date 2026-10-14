// A bounded, fictional, one-wave relief-cargo matching problem. These scenario
// limits are educational rules, not aviation or operational guidance.
const AGENTS = ['fleet', 'crew', 'weather', 'airport', 'cargo'];
const CATEGORIES = ['medical', 'food', 'water', 'equipment'];
const ID = /^SIM-[A-Za-z0-9_-]{1,64}$/;
const isId = value => typeof value === 'string' && ID.test(value);
const ASSIGNMENT_KEYS = ['requestId', 'aircraftId', 'crewId', 'departureSlot', 'arrivalSlot'];
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const sorted = (items, key = 'id') => [...items].sort((a, b) => compare(a[key], b[key]));
const fresh = (entity, world) => entity.validThroughTick >= world.tick;
const uniqueSorted = values => [...new Set(values)].sort(compare);
const finite = (n, min, max) => typeof n === 'number' && Number.isFinite(n) && n >= min && n <= max;
const integer = (n, min, max) => Number.isInteger(n) && finite(n, min, max);

function assertWorld(w) {
  const fail = () => { throw new TypeError('Invalid bounded fictional relief world'); };
  if (!w || w.version !== 1 || w.simulation !== true ||
      typeof w.runId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(w.runId) ||
      !integer(w.revision, 0, 20) || !integer(w.tick, 0, 10)) fail();
  const p = w.policy;
  if (!p || JSON.stringify(p.slots) !== '[0,1,2]' || p.slotMinutes !== 30 || p.minVisibilityM !== 3000 || p.maxWindSpeedMps !== 15) fail();
  for (const [name, max] of Object.entries({ aircraft: 3, crews: 3, airports: 3, weather: 3, routes: 2, requests: 5, demandHistory: 31 })) {
    if (!Array.isArray(w[name]) || w[name].length > max || w[name].some(e => !e || typeof e !== 'object' || Array.isArray(e))) fail();
  }
  const allIds = [];
  for (const name of ['aircraft', 'crews', 'airports', 'requests']) {
    for (const e of w[name]) {
      if (!isId(e.id) || !integer(e.validThroughTick, 0, 10)) fail();
      allIds.push(e.id);
    }
  }
  if (new Set(allIds).size !== allIds.length) fail();
  for (const a of w.aircraft) {
    if (!isId(a.airportId) || !finite(a.capacityKg, 0, 1000000) || typeof a.coldStorage !== 'boolean' ||
        !['available', 'maintenance', 'unavailable'].includes(a.status)) fail();
  }
  for (const c of w.crews) {
    if (!['available', 'rest', 'unavailable'].includes(c.status) || !Array.isArray(c.qualifications) || c.qualifications.length > 8 ||
        c.qualifications.some(q => typeof q !== 'string' || !/^[a-z-]{1,64}$/.test(q)) ||
        !integer(c.fromSlot, 0, 4) || !integer(c.toSlot, c.fromSlot, 4)) fail();
  }
  for (const a of w.airports) {
    if (!['open', 'restricted', 'closed'].includes(a.status) || !integer(a.arrivalsPerSlot, 0, 3) || !integer(a.departuresPerSlot, 0, 3)) fail();
  }
  for (const v of w.weather) {
    if (!isId(v.airportId) || !finite(v.windSpeedMps, 0, 1000) || !finite(v.visibilityM, 0, 1000000) ||
        typeof v.condition !== 'string' || v.condition.length > 80 || !integer(v.validThroughTick, 0, 10)) fail();
  }
  if (new Set(w.weather.map(v => v.airportId)).size !== w.weather.length) fail();
  for (const r of w.routes) if (!isId(r.originId) || !isId(r.destinationId) || r.originId === r.destinationId || r.durationSlots !== 1) fail();
  if (new Set(w.routes.map(r => `${r.originId}|${r.destinationId}`)).size !== w.routes.length) fail();
  for (const r of w.requests) {
    if (!CATEGORIES.includes(r.category) || !finite(r.massKg, Number.MIN_VALUE, 1000000) || !isId(r.originId) ||
        !isId(r.destinationId) || r.originId === r.destinationId || typeof r.temperatureControlled !== 'boolean' ||
        !integer(r.priority, 1, 5) || !integer(r.deadlineSlot, 1, 4)) fail();
  }
  for (const d of w.demandHistory) if (!integer(d.day, 0, 1000000) || !integer(d.demand, 0, 1000000)) fail();
  if (new Set(w.demandHistory.map(d => d.day)).size !== w.demandHistory.length) fail();
}

function assertPrevious(previousAssignments) {
  if (!Array.isArray(previousAssignments) || previousAssignments.length > 5 ||
      previousAssignments.some(a => !assignmentShape(a)) ||
      new Set(previousAssignments.map(a => a.requestId)).size !== previousAssignments.length) {
    throw new TypeError('Invalid previousAssignments');
  }
}

function assignmentShape(a) {
  return a && typeof a === 'object' && !Array.isArray(a) &&
    Object.keys(a).length === ASSIGNMENT_KEYS.length && ASSIGNMENT_KEYS.every(k => Object.hasOwn(a, k)) &&
    isId(a.requestId) && isId(a.aircraftId) && isId(a.crewId) &&
    integer(a.departureSlot, 0, 2) && integer(a.arrivalSlot, 1, 4);
}

function fleetCodes(a, w) {
  return [a.status !== 'available' && 'FLEET_UNAVAILABLE', !fresh(a, w) && 'FLEET_EXPIRED'].filter(Boolean);
}
function crewCodes(c, w) {
  return [c.status !== 'available' && 'CREW_UNAVAILABLE', !fresh(c, w) && 'CREW_EXPIRED',
    !c.qualifications.includes('relief-pilot') && 'CREW_UNQUALIFIED'].filter(Boolean);
}
function airportCodes(a, w) {
  if (!a) return ['AIRPORT_MISSING'];
  return [a.status === 'closed' && 'AIRPORT_CLOSED', !fresh(a, w) && 'AIRPORT_EXPIRED',
    a.arrivalsPerSlot === 0 && a.departuresPerSlot === 0 && 'AIRPORT_NO_CAPACITY'].filter(Boolean);
}
function weatherCodes(v, w) {
  if (!v) return ['WEATHER_MISSING'];
  return [!fresh(v, w) && 'WEATHER_EXPIRED', v.windSpeedMps > w.policy.maxWindSpeedMps && 'WEATHER_WIND_BLOCKED',
    v.visibilityM < w.policy.minVisibilityM && 'WEATHER_VISIBILITY_BLOCKED'].filter(Boolean);
}
function cargoCodes(r, w) {
  return [!fresh(r, w) && 'CARGO_EXPIRED',
    !w.routes.some(v => v.originId === r.originId && v.destinationId === r.destinationId) && 'ROUTE_MISSING'].filter(Boolean);
}

const MESSAGES = {
  ELIGIBLE: 'Current scenario evidence permits this entity for its specialist checks.',
  FLEET_UNAVAILABLE: 'The fictional aircraft is not available.', FLEET_EXPIRED: 'Aircraft evidence has expired at the current logical tick.',
  CREW_UNAVAILABLE: 'The fictional crew is not available.', CREW_EXPIRED: 'Crew evidence has expired at the current logical tick.',
  CREW_UNQUALIFIED: 'The crew lacks the relief-pilot scenario qualification.',
  AIRPORT_MISSING: 'Required airport evidence is missing.', AIRPORT_CLOSED: 'The fictional airport is closed.',
  AIRPORT_EXPIRED: 'Airport evidence has expired at the current logical tick.', AIRPORT_NO_CAPACITY: 'The airport has no scenario slot capacity.',
  WEATHER_MISSING: 'Required scenario weather evidence is missing.', WEATHER_EXPIRED: 'Weather evidence has expired at the current logical tick.',
  WEATHER_WIND_BLOCKED: 'Scenario wind exceeds the fixed educational limit.', WEATHER_VISIBILITY_BLOCKED: 'Scenario visibility is below the fixed educational limit.',
  CARGO_EXPIRED: 'Request evidence has expired at the current logical tick.', ROUTE_MISSING: 'No one-wave scenario route connects the request endpoints.',
};

function buildReports(w) {
  const weatherIds = uniqueSorted([...w.airports.map(a => a.id), ...w.requests.flatMap(r => [r.originId, r.destinationId])]);
  const sources = {
    fleet: sorted(w.aircraft).map(a => [a.id, fleetCodes(a, w)]),
    crew: sorted(w.crews).map(c => [c.id, crewCodes(c, w)]),
    weather: weatherIds.map(id => [id, weatherCodes(w.weather.find(v => v.airportId === id), w)]),
    airport: uniqueSorted([...w.airports.map(a => a.id), ...w.requests.flatMap(r => [r.originId, r.destinationId])])
      .map(id => [id, airportCodes(w.airports.find(a => a.id === id), w)]),
    cargo: sorted(w.requests).map(r => [r.id, cargoCodes(r, w)]),
  };
  return AGENTS.map(agentId => ({
    agentId,
    findings: sources[agentId].flatMap(([id, codes]) => (codes.length ? uniqueSorted(codes) : ['ELIGIBLE']).map(code => ({
      id: `SIM-FIND-${agentId}-${id.slice(4)}-${code}`, code, message: MESSAGES[code], entityIds: [id],
    }))),
    eligibleIds: sources[agentId].filter(([, codes]) => codes.length === 0).map(([id]) => id),
  }));
}

function candidatesFor(r, w) {
  const candidates = [], rejected = new Set(cargoCodes(r, w));
  for (const id of [r.originId, r.destinationId]) {
    for (const code of airportCodes(w.airports.find(a => a.id === id), w)) rejected.add(code);
    for (const code of weatherCodes(w.weather.find(v => v.airportId === id), w)) rejected.add(code);
  }
  const blocking = rejected.size > 0;
  if (!w.aircraft.length) rejected.add('FLEET_MISSING');
  if (!w.crews.length) rejected.add('CREW_MISSING');
  for (const a of sorted(w.aircraft)) for (const c of sorted(w.crews)) for (const slot of w.policy.slots) {
    const codes = [...fleetCodes(a, w), ...crewCodes(c, w)];
    if (a.airportId !== r.originId) codes.push('FLEET_WRONG_ORIGIN');
    if (a.capacityKg < r.massKg) codes.push('PAYLOAD_EXCEEDED');
    if (r.temperatureControlled && !a.coldStorage) codes.push('COLD_STORAGE_REQUIRED');
    const arrivalSlot = slot + 1;
    if (c.fromSlot > slot || c.toSlot < arrivalSlot) codes.push('CREW_DUTY_EXCEEDED');
    if (arrivalSlot > r.deadlineSlot) codes.push('DEADLINE_EXCEEDED');
    if ((w.airports.find(v => v.id === r.originId)?.departuresPerSlot ?? 0) < 1) codes.push('DEPARTURE_CAPACITY_EXCEEDED');
    if ((w.airports.find(v => v.id === r.destinationId)?.arrivalsPerSlot ?? 0) < 1) codes.push('ARRIVAL_CAPACITY_EXCEEDED');
    for (const code of codes) rejected.add(code);
    if (!blocking && codes.length === 0) candidates.push({ requestId: r.id, aircraftId: a.id, crewId: c.id, departureSlot: slot, arrivalSlot });
  }
  return { candidates, reasonCodes: uniqueSorted([...rejected]) };
}

function sameAssignment(a, b) {
  return a && b && ASSIGNMENT_KEYS.every(k => a[k] === b[k]);
}
function objectiveFor(w, assignments, previousAssignments) {
  const byRequest = new Map(assignments.map(a => [a.requestId, a]));
  const surviving = new Set(w.requests.map(r => r.id));
  return {
    servedPriority: w.requests.reduce((total, r) => total + (byRequest.has(r.id) ? r.priority : 0), 0),
    changedAssignments: previousAssignments.filter(a => surviving.has(a.requestId) && !sameAssignment(a, byRequest.get(a.requestId))).length,
    totalArrivalSlots: assignments.reduce((total, a) => total + a.arrivalSlot, 0),
  };
}
function assignmentKey(assignments) {
  return sorted(assignments, 'requestId').map(a => `${a.requestId}|${a.aircraftId}|${a.crewId}|${a.departureSlot}|${a.arrivalSlot}`).join(';');
}
function better(a, b) {
  return a.objective.servedPriority > b.objective.servedPriority ||
    (a.objective.servedPriority === b.objective.servedPriority && (
      a.objective.changedAssignments < b.objective.changedAssignments ||
      (a.objective.changedAssignments === b.objective.changedAssignments && (
        a.objective.totalArrivalSlots < b.objective.totalArrivalSlots ||
        (a.objective.totalArrivalSlots === b.objective.totalArrivalSlots && compare(assignmentKey(a.assignments), assignmentKey(b.assignments)) < 0)))));
}

export function optimizeReliefWorld(world, { previousAssignments = [], nodeLimit = 100000 } = {}) {
  assertWorld(world);
  assertPrevious(previousAssignments);
  if (!integer(nodeLimit, 1, 100000)) throw new RangeError('nodeLimit must be an integer from 1 to 100000');
  const requests = sorted(world.requests);
  const agentReports = buildReports(world);
  const eligibility = Object.fromEntries(agentReports.map(report => [report.agentId, new Set(report.eligibleIds)]));
  // The supervisor consumes specialist eligibility first, then applies cargo,
  // duty, timing and shared-resource constraints to its finite candidates.
  const options = requests.map(r => {
    const evidence = candidatesFor(r, world);
    return { ...evidence, candidates: evidence.candidates.filter(a =>
      eligibility.fleet.has(a.aircraftId) && eligibility.crew.has(a.crewId) && eligibility.cargo.has(r.id) &&
      [r.originId, r.destinationId].every(id => eligibility.weather.has(id) && eligibility.airport.has(id))) };
  });
  let best = { assignments: [], objective: objectiveFor(world, [], previousAssignments) };
  let nodesExplored = 0, budgetExhausted = false;
  const usedAircraft = new Set(), usedCrews = new Set(), departures = new Map(), arrivals = new Map();
  const chosen = [];
  function visit(index, priority) {
    if (nodesExplored >= nodeLimit) { budgetExhausted = true; return; }
    nodesExplored++;
    // Every partial assignment is already feasible: it is a useful incumbent
    // even when there is insufficient budget to reach a full leaf.
    const incumbent = { assignments: [...chosen], objective: objectiveFor(world, chosen, previousAssignments) };
    if (better(incumbent, best)) best = incumbent;
    if (index === requests.length || priority + requests.slice(index).reduce((sum, r) => sum + r.priority, 0) < best.objective.servedPriority) return;
    const request = requests[index];
    for (const a of options[index].candidates) {
      if (usedAircraft.has(a.aircraftId) || usedCrews.has(a.crewId)) continue;
      const dk = `${request.originId}|${a.departureSlot}`, ak = `${request.destinationId}|${a.arrivalSlot}`;
      const dc = departures.get(dk) ?? 0, ac = arrivals.get(ak) ?? 0;
      if (dc >= world.airports.find(v => v.id === request.originId).departuresPerSlot || ac >= world.airports.find(v => v.id === request.destinationId).arrivalsPerSlot) continue;
      usedAircraft.add(a.aircraftId); usedCrews.add(a.crewId); departures.set(dk, dc + 1); arrivals.set(ak, ac + 1); chosen.push(a);
      visit(index + 1, priority + request.priority);
      chosen.pop(); usedAircraft.delete(a.aircraftId); usedCrews.delete(a.crewId); departures.set(dk, dc); arrivals.set(ak, ac);
      if (budgetExhausted) return;
    }
    visit(index + 1, priority);
  }
  visit(0, 0);
  const served = new Set(best.assignments.map(a => a.requestId));
  return {
    status: budgetExhausted ? 'feasible_budget' : 'optimal',
    assignments: sorted(best.assignments, 'requestId'),
    unserved: requests.flatMap((r, i) => served.has(r.id) ? [] : [{ requestId: r.id, reasonCodes: options[i].candidates.length ?
      [budgetExhausted ? 'SEARCH_BUDGET_EXHAUSTED' : 'RESOURCE_CONTENTION_OR_PRIORITY'] : options[i].reasonCodes }]),
    objective: best.objective,
    diagnostics: { method: 'bounded-exact-one-wave', nodesExplored, nodeLimit, budgetExhausted, candidateCount: options.reduce((n, o) => n + o.candidates.length, 0) },
    agentReports,
  };
}

// This checker does not trust specialist eligibility, candidate generation or
// search bookkeeping. It walks the assignments and original world evidence.
// It certifies feasibility and objective arithmetic, not global optimality.
export function validateReliefPlan(world, plan, { previousAssignments = [] } = {}) {
  const errors = [];
  try { assertWorld(world); assertPrevious(previousAssignments); }
  catch (error) { return { valid: false, errors: [error.message] }; }
  if (!plan || !Array.isArray(plan.assignments) || plan.assignments.length > 5 ||
      !Array.isArray(plan.unserved) || plan.unserved.length > 5) return { valid: false, errors: ['Invalid plan shape'] };
  const requests = new Map(world.requests.map(r => [r.id, r]));
  const aircraft = new Map(world.aircraft.map(a => [a.id, a]));
  const crews = new Map(world.crews.map(c => [c.id, c]));
  const airports = new Map(world.airports.map(a => [a.id, a]));
  const weather = new Map(world.weather.map(v => [v.airportId, v]));
  const seen = { requestId: new Set(), aircraftId: new Set(), crewId: new Set() };
  const departures = new Map(), arrivals = new Map();
  let priority = 0, arrivalSum = 0;
  for (const assignment of plan.assignments) {
    if (!assignmentShape(assignment)) { errors.push('Invalid assignment shape or slots'); continue; }
    for (const key of ['requestId', 'aircraftId', 'crewId']) {
      if (seen[key].has(assignment[key])) errors.push(`Duplicate ${key}: ${assignment[key]}`);
      seen[key].add(assignment[key]);
    }
    const r = requests.get(assignment.requestId), a = aircraft.get(assignment.aircraftId), c = crews.get(assignment.crewId);
    if (!r || !a || !c) { errors.push('Unknown assignment entity ID'); continue; }
    priority += r.priority; arrivalSum += assignment.arrivalSlot;
    if (!world.policy.slots.includes(assignment.departureSlot)) errors.push('Illegal departure slot');
    const route = world.routes.find(v => v.originId === r.originId && v.destinationId === r.destinationId);
    if (!route || assignment.arrivalSlot !== assignment.departureSlot + route.durationSlots) errors.push('Missing route or incorrect arrival');
    if (a.status !== 'available' || a.validThroughTick < world.tick) errors.push('Aircraft unavailable or expired');
    if (a.airportId !== r.originId) errors.push('Aircraft origin mismatch');
    if (a.capacityKg < r.massKg) errors.push('Payload capacity exceeded');
    if (r.temperatureControlled && !a.coldStorage) errors.push('Cold storage required');
    if (c.status !== 'available' || c.validThroughTick < world.tick) errors.push('Crew unavailable or expired');
    if (!c.qualifications.includes('relief-pilot')) errors.push('Crew qualification missing');
    if (assignment.departureSlot < c.fromSlot || assignment.arrivalSlot > c.toSlot) errors.push('Crew duty exceeded');
    if (r.validThroughTick < world.tick) errors.push('Request expired');
    if (assignment.arrivalSlot > r.deadlineSlot) errors.push('Request deadline exceeded');
    for (const id of [r.originId, r.destinationId]) {
      const airport = airports.get(id), evidence = weather.get(id);
      if (!airport || airport.status === 'closed' || airport.validThroughTick < world.tick) errors.push(`Airport blocked or missing: ${id}`);
      if (!evidence || evidence.validThroughTick < world.tick || evidence.windSpeedMps > world.policy.maxWindSpeedMps || evidence.visibilityM < world.policy.minVisibilityM) errors.push(`Weather blocked or missing: ${id}`);
    }
    const dk = `${r.originId}|${assignment.departureSlot}`, ak = `${r.destinationId}|${assignment.arrivalSlot}`;
    departures.set(dk, (departures.get(dk) ?? 0) + 1); arrivals.set(ak, (arrivals.get(ak) ?? 0) + 1);
  }
  for (const [key, count] of departures) if (count > (airports.get(key.split('|')[0])?.departuresPerSlot ?? 0)) errors.push('Airport departure capacity exceeded');
  for (const [key, count] of arrivals) if (count > (airports.get(key.split('|')[0])?.arrivalsPerSlot ?? 0)) errors.push('Airport arrival capacity exceeded');
  let changed = 0;
  for (const prior of previousAssignments) {
    if (!requests.has(prior.requestId)) continue;
    const current = plan.assignments.find(a => a?.requestId === prior.requestId);
    if (!current || ASSIGNMENT_KEYS.some(key => current[key] !== prior[key])) changed++;
  }
  const expectedObjective = { servedPriority: priority, changedAssignments: changed, totalArrivalSlots: arrivalSum };
  if (!plan.objective || Object.keys(plan.objective).length !== 3 || Object.entries(expectedObjective).some(([k, v]) => plan.objective[k] !== v)) errors.push('Objective mismatch');
  const unservedIds = new Set();
  const optionEvidence = new Map(world.requests.map(r => [r.id, candidatesFor(r, world)]));
  for (const entry of plan.unserved) {
    if (!entry || !requests.has(entry.requestId) || seen.requestId.has(entry.requestId) || unservedIds.has(entry.requestId) ||
        !Array.isArray(entry.reasonCodes) || entry.reasonCodes.length === 0 || entry.reasonCodes.some(c => typeof c !== 'string' || !/^[A-Z_]{1,64}$/.test(c))) errors.push('Invalid unserved request');
    const evidence = optionEvidence.get(entry?.requestId);
    if (evidence) {
      const expectedReasons = evidence.candidates.length ?
        [plan.status === 'feasible_budget' ? 'SEARCH_BUDGET_EXHAUSTED' : 'RESOURCE_CONTENTION_OR_PRIORITY'] : evidence.reasonCodes;
      if (JSON.stringify(entry.reasonCodes) !== JSON.stringify(expectedReasons)) errors.push('Unserved reason evidence mismatch');
    }
    if (entry) unservedIds.add(entry.requestId);
  }
  for (const id of requests.keys()) if (!seen.requestId.has(id) && !unservedIds.has(id)) errors.push('Request omitted from plan');
  // Canonical reports are finite facts, including messages; an LLM cannot add
  // entities, eligibility claims or alternative prose to this evidence channel.
  if (!reportsEqual(plan.agentReports, buildReports(world))) errors.push('Specialist evidence mismatch');
  const d = plan.diagnostics;
  if (!d || d.method !== 'bounded-exact-one-wave' || d.candidateCount !== [...optionEvidence.values()].reduce((sum, o) => sum + o.candidates.length, 0) ||
      !integer(d.nodeLimit, 1, 100000) || !integer(d.nodesExplored, 1, d.nodeLimit) || typeof d.budgetExhausted !== 'boolean' ||
      !['optimal', 'feasible_budget'].includes(plan.status) || (plan.status === 'optimal') === d.budgetExhausted ||
      (d.budgetExhausted && d.nodesExplored !== d.nodeLimit)) errors.push('Invalid search status or budget');
  return { valid: errors.length === 0, errors: uniqueSorted(errors) };
}

function reportsEqual(actual, expected) {
  if (!Array.isArray(actual) || actual.length !== expected.length) return false;
  return expected.every((report, i) => {
    const candidate = actual[i];
    if (!candidate || candidate.agentId !== report.agentId || !Array.isArray(candidate.eligibleIds) || !Array.isArray(candidate.findings) ||
        JSON.stringify(candidate.eligibleIds) !== JSON.stringify(report.eligibleIds) || candidate.findings.length !== report.findings.length) return false;
    return report.findings.every((finding, j) => {
      const proposed = candidate.findings[j];
      return proposed && Object.keys(proposed).length === 4 && proposed.id === finding.id && proposed.code === finding.code &&
        proposed.message === finding.message && JSON.stringify(proposed.entityIds) === JSON.stringify(finding.entityIds);
    });
  });
}
