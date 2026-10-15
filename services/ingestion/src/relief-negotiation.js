import { z } from 'zod';
import { canonicalJson } from './contracts.js';
import { getReliefNegotiationContext, validateReliefAssignmentSeed } from './relief-planner.js';

export const negotiationSettingsSchema = z.strictObject({
  enabled: z.boolean().default(true),
  maxRounds: z.number().int().min(1).max(8).default(4),
  maxMessages: z.number().int().min(32).max(512).default(512),
});
const ROLES = Object.freeze(['fleet', 'crew', 'weather', 'airport', 'cargo']);
const unique = values => [...new Set(values)].sort();
const order = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const same = (a, b) => ['requestId', 'aircraftId', 'crewId', 'departureSlot', 'arrivalSlot'].every(k => a[k] === b[k]);
const canonicalAssignments = assignments => [...assignments].sort((a, b) => order(a.requestId, b.requestId));

function localChecks(role, world, assignment, reserved) {
  const request = world.requests.find(r => r.id === assignment.requestId);
  const aircraft = world.aircraft.find(a => a.id === assignment.aircraftId);
  const crew = world.crews.find(c => c.id === assignment.crewId);
  const codes = [], entityIds = [];
  if (role === 'fleet') {
    entityIds.push(aircraft.id);
    if (aircraft.status !== 'available') codes.push('FLEET_UNAVAILABLE');
    if (aircraft.validThroughTick < world.tick) codes.push('FLEET_EXPIRED');
    if (aircraft.airportId !== request.originId) codes.push('FLEET_WRONG_ORIGIN');
    if (aircraft.capacityKg < request.massKg) codes.push('PAYLOAD_EXCEEDED');
    if (request.temperatureControlled && !aircraft.coldStorage) codes.push('COLD_STORAGE_REQUIRED');
    if (reserved.some(a => a.aircraftId === aircraft.id)) codes.push('AIRCRAFT_RESERVED');
  } else if (role === 'crew') {
    entityIds.push(crew.id);
    if (crew.status !== 'available') codes.push('CREW_UNAVAILABLE');
    if (crew.validThroughTick < world.tick) codes.push('CREW_EXPIRED');
    if (!crew.qualifications.includes('relief-pilot')) codes.push('CREW_UNQUALIFIED');
    if (assignment.departureSlot < crew.fromSlot || assignment.arrivalSlot > crew.toSlot) codes.push('CREW_DUTY_EXCEEDED');
    if (reserved.some(a => a.crewId === crew.id)) codes.push('CREW_RESERVED');
  } else if (role === 'weather') {
    for (const id of [request.originId, request.destinationId]) {
      entityIds.push(id);
      const weather = world.weather.find(w => w.airportId === id);
      if (!weather) codes.push('WEATHER_MISSING');
      else {
        if (weather.validThroughTick < world.tick) codes.push('WEATHER_EXPIRED');
        if (weather.windSpeedMps > world.policy.maxWindSpeedMps) codes.push('WEATHER_WIND_BLOCKED');
        if (weather.visibilityM < world.policy.minVisibilityM) codes.push('WEATHER_VISIBILITY_BLOCKED');
      }
    }
  } else if (role === 'airport') {
    for (const id of [request.originId, request.destinationId]) {
      entityIds.push(id);
      const airport = world.airports.find(a => a.id === id);
      if (!airport || airport.status === 'closed') codes.push('AIRPORT_CLOSED_OR_MISSING');
      else if (airport.validThroughTick < world.tick) codes.push('AIRPORT_EXPIRED');
    }
    const departures = reserved.filter(a => a.departureSlot === assignment.departureSlot && world.requests.find(r => r.id === a.requestId).originId === request.originId).length;
    const arrivals = reserved.filter(a => a.arrivalSlot === assignment.arrivalSlot && world.requests.find(r => r.id === a.requestId).destinationId === request.destinationId).length;
    if (departures >= (world.airports.find(a => a.id === request.originId)?.departuresPerSlot ?? 0)) codes.push('DEPARTURE_CAPACITY_EXCEEDED');
    if (arrivals >= (world.airports.find(a => a.id === request.destinationId)?.arrivalsPerSlot ?? 0)) codes.push('ARRIVAL_CAPACITY_EXCEEDED');
  } else {
    entityIds.push(request.id);
    if (request.validThroughTick < world.tick) codes.push('CARGO_EXPIRED');
    const route = world.routes.find(r => r.originId === request.originId && r.destinationId === request.destinationId);
    if (!route || assignment.arrivalSlot !== assignment.departureSlot + route.durationSlots) codes.push('ROUTE_MISSING');
    if (assignment.arrivalSlot > request.deadlineSlot) codes.push('DEADLINE_EXCEEDED');
    if (reserved.some(a => a.requestId === request.id)) codes.push('REQUEST_RESERVED');
  }
  return { ruleCodes: unique(codes), entityIds: unique(entityIds) };
}

// Preferences only rank legal counterbids. Every agent's veto remains mandatory.
function preference(role, world, candidate, previous) {
  const a = candidate.assignment, request = world.requests.find(r => r.id === a.requestId);
  const aircraft = world.aircraft.find(v => v.id === a.aircraftId), crew = world.crews.find(v => v.id === a.crewId);
  const retained = previous.some(p => same(p, a)) ? 0 : 1;
  if (role === 'fleet') return [retained, !request.temperatureControlled && aircraft.coldStorage ? 1 : 0, aircraft.capacityKg - request.massKg, a.arrivalSlot];
  if (role === 'crew') return [retained, crew.toSlot - crew.fromSlot, a.arrivalSlot];
  if (role === 'airport') return [retained, a.departureSlot, a.arrivalSlot];
  return [retained, a.arrivalSlot, a.departureSlot];
}
function ranked(role, world, candidates, previous) {
  return [...candidates].sort((a, b) => {
    const left = preference(role, world, a, previous), right = preference(role, world, b, previous);
    for (let i = 0; i < left.length; i++) if (left[i] !== right[i]) return left[i] - right[i];
    return order(a.id, b.id);
  });
}

class Specialist {
  constructor(agentId, world, report, previous) {
    this.agentId = agentId; this.world = world; this.report = report; this.previous = previous;
    this.reserved = []; this.inbox = []; this.acceptedProposalIds = []; this.rejectedProposalIds = []; this.bidsSent = 0;
  }
  receive(message) {
    this.inbox.push(message);
    if (message.kind === 'commit') this.reserved.push(message.assignment);
  }
  evaluate(candidate) {
    const evidence = localChecks(this.agentId, this.world, candidate.assignment, this.reserved);
    return { ...evidence, findingIds: this.report.findings.filter(f => f.entityIds.some(id => evidence.entityIds.includes(id))).map(f => f.id) };
  }
  bid(candidates) { return ranked(this.agentId, this.world, candidates.filter(c => !this.evaluate(c).ruleCodes.length), this.previous); }
  counter(requestId, candidates, tried) {
    const advertised = new Map(this.inbox.filter(m => m.kind === 'bid' && m.requestId === requestId).map(m => [m.from, new Set(m.candidateIds)]));
    const local = this.bid(candidates);
    return local.find(c => !tried.has(c.id) && ROLES.filter(r => r !== this.agentId).every(r => advertised.get(r)?.has(c.id)));
  }
}

export function runReliefNegotiation(world, { previousAssignments = [], settings = {} } = {}) {
  const config = negotiationSettingsSchema.parse(settings), context = getReliefNegotiationContext(world);
  const seedCheck = validateReliefAssignmentSeed(world, [], { previousAssignments });
  if (!seedCheck.valid) throw new TypeError('Invalid negotiation context.');
  const report = { version: 1, runId: world.runId, revision: world.revision, mode: 'deterministic-autonomous', topology: 'fully-connected-peers',
    settings: config, previousAssignments: structuredClone(previousAssignments), status: config.enabled ? 'no_agreement' : 'disabled', roundsCompleted: 0, requests: [], agentStates: [], messages: [], assignments: [] };
  if (!config.enabled) return report;
  const snapshot = structuredClone(world);
  const actors = new Map(context.agentReports.map(r => [r.agentId, new Specialist(r.agentId, snapshot, r, previousAssignments)]));
  const byId = new Map(context.candidates.map(c => [c.id, c]));
  let exhausted = false;
  function broadcast(from, kind, fields, recipients = [...ROLES.filter(r => r !== from), 'supervisor']) {
    // Reserve the entire delivery group before touching mailboxes or transcript.
    if (report.messages.length + recipients.length > config.maxMessages) { exhausted = true; return false; }
    for (const to of recipients) {
      const message = { id: `SIM-NEG-${world.runId}-${world.revision}-${report.messages.length + 1}`, from, to, kind,
        entityIds: [], findingIds: [], ruleCodes: [], ...fields };
      report.messages.push(message); actors.get(to)?.receive(message);
    }
    return true;
  }
  const requests = [...world.requests].sort((a, b) => b.priority - a.priority || order(a.id, b.id));
  for (const request of requests) {
    const state = { requestId: request.id, status: 'deferred', rounds: 0 };
    report.requests.push(state);
    if (exhausted) { state.status = 'budget_exhausted'; continue; }
    const candidates = context.candidates.filter(c => c.assignment.requestId === request.id), tried = new Set();
    const cargo = actors.get('cargo');
    if (!broadcast('cargo', 'cfp', { round: 0, requestId: request.id, entityIds: [request.id], summary: 'Cargo requests peer proposals for this relief request.' }, ROLES.filter(r => r !== 'cargo'))) { state.status = 'budget_exhausted'; continue; }
    let proposal = ranked('cargo', snapshot, candidates, previousAssignments)[0];
    if (!proposal) state.status = 'blocked';
    for (let round = 1; round <= config.maxRounds && proposal; round++) {
      state.rounds = round; report.roundsCompleted++;
      const proposalId = `SIM-PROP-${world.runId}-${world.revision}-${request.id.slice(4)}-${round}`;
      const common = { round, requestId: request.id, proposalId, candidateId: proposal.id, assignment: proposal.assignment };
      if (!broadcast('cargo', 'proposal', { ...common, entityIds: [request.id, proposal.assignment.aircraftId, proposal.assignment.crewId], summary: 'Cargo proposes this candidate for peer evaluation.' })) break;
      tried.add(proposal.id);
      const votes = ROLES.map(role => ({ role, evidence: actors.get(role).evaluate(proposal) }));
      // A full voting round must fit; no partially delivered vote set can become consensus.
      if (report.messages.length + ROLES.length * ROLES.length > config.maxMessages) { exhausted = true; break; }
      for (const { role, evidence } of votes) {
        const accepted = evidence.ruleCodes.length === 0, actor = actors.get(role);
        broadcast(role, accepted ? 'accept' : 'reject', { ...common, ...evidence, summary: accepted ? `${role} accepts under its local constraints.` : `${role} objects under its local constraints.` });
        (accepted ? actor.acceptedProposalIds : actor.rejectedProposalIds).push(proposalId);
      }
      const objections = votes.filter(v => v.evidence.ruleCodes.length);
      const supervisorVotes = report.messages.filter(m => m.to === 'supervisor' && m.proposalId === proposalId && m.kind === 'accept');
      if (!objections.length && new Set(supervisorVotes.map(m => m.from)).size === ROLES.length) {
        if (!broadcast('supervisor', 'commit', { ...common, entityIds: [request.id, proposal.assignment.aircraftId, proposal.assignment.crewId], summary: 'All five peers accepted; supervisor reserves this candidate in the negotiated incumbent.' }, ROLES)) break;
        report.assignments.push({ ...proposal.assignment }); state.status = 'agreed'; state.assignment = { ...proposal.assignment }; break;
      }
      // Each independent specialist advertises only its own locally acceptable candidates.
      if (report.messages.length + ROLES.length * ROLES.length > config.maxMessages) { exhausted = true; break; }
      for (const role of ROLES) {
        const actor = actors.get(role), ids = actor.bid(candidates).map(c => c.id);
        broadcast(role, 'bid', { round, requestId: request.id, proposalId, candidateIds: ids, entityIds: [request.id], summary: `${role} advertises locally acceptable candidate IDs.` }); actor.bidsSent++;
      }
      const counterbids = [];
      for (const { role } of objections) {
        const counter = actors.get(role).counter(request.id, candidates, tried);
        if (!counter) continue;
        if (!broadcast(role, 'counterproposal', { round, requestId: request.id, proposalId, candidateId: counter.id, assignment: counter.assignment,
          entityIds: [request.id, counter.assignment.aircraftId, counter.assignment.crewId], summary: `${role} proposes an alternative supported by the advertised peer bids.` })) break;
        counterbids.push(counter);
      }
      if (exhausted) break;
      // Cargo consumes actual received counterproposals, not a centralized substitute vote.
      const received = cargo.inbox.filter(m => m.kind === 'counterproposal' && m.proposalId === proposalId).map(m => byId.get(m.candidateId));
      const own = counterbids.filter(c => !received.includes(c));
      const alternatives = [...new Map([...received, ...own].map(c => [c.id, c])).values()];
      proposal = ranked('cargo', snapshot, alternatives, previousAssignments)[0];
      if (!proposal) { state.status = 'blocked'; break; }
    }
    if (exhausted) state.status = 'budget_exhausted';
    if (state.status !== 'agreed' && !exhausted) broadcast('supervisor', 'defer', { round: state.rounds, requestId: request.id, entityIds: [request.id], summary: state.status === 'blocked' ? 'No untried candidate has joint peer support; request deferred to final optimization.' : 'Negotiation round limit reached; request deferred to final optimization.' }, ROLES);
  }
  report.assignments = canonicalAssignments(report.assignments);
  report.agentStates = [...actors.values()].map(a => ({ agentId: a.agentId, acceptedProposalIds: unique(a.acceptedProposalIds), rejectedProposalIds: unique(a.rejectedProposalIds), bidsSent: a.bidsSent }));
  report.status = exhausted ? 'budget_exhausted' : report.requests.every(r => r.status === 'agreed') && report.assignments.length ? 'agreed' : report.assignments.length ? 'partial' : 'no_agreement';
  if (!validateReliefAssignmentSeed(world, report.assignments, { previousAssignments }).valid) throw new Error('Negotiated incumbent failed independent verification.');
  return report;
}

/** Audit the executed transcript independently before accepting its incumbent. */
export function validateReliefNegotiationReport(world, report, { previousAssignments = report?.previousAssignments ?? [] } = {}) {
  const errors = [];
  try {
    const context = getReliefNegotiationContext(world);
    if (!report || report.runId !== world.runId || report.revision !== world.revision || report.version !== 1 ||
        report.mode !== 'deterministic-autonomous' || report.topology !== 'fully-connected-peers') throw new Error('Negotiation identity mismatch.');
    const settings = negotiationSettingsSchema.parse(report.settings);
    if (!['agreed','partial','no_agreement','budget_exhausted','failed','disabled'].includes(report.status) ||
        !Array.isArray(report.messages) || report.messages.length > settings.maxMessages) throw new Error('Invalid negotiation status or budget.');
    if (!Number.isInteger(report.roundsCompleted) || report.roundsCompleted < 0 || report.roundsCompleted > world.requests.length * settings.maxRounds ||
        !Array.isArray(report.requests) || !Array.isArray(report.agentStates)) throw new Error('Invalid negotiation state summary.');
    if (canonicalJson(report.previousAssignments) !== canonicalJson(previousAssignments)) throw new Error('Negotiation prior context mismatch.');
    if (report.status === 'failed') {
      if (report.errorCode !== 'NEGOTIATION_FAILED' || report.roundsCompleted || report.requests.length || report.agentStates.length) throw new Error('Invalid negotiation failure.');
    } else {
      // Deterministic policy replay binds every mailbox delivery, bid/counter causality,
      // entity/evidence reference and state summary to this exact world and prior plan.
      // Feasibility and unanimous commits are still checked separately below.
      const expected = runReliefNegotiation(world, { previousAssignments, settings });
      const { outcome, ...executed } = report;
      if (canonicalJson(executed) !== canonicalJson(expected)) throw new Error('Negotiation transcript does not match executed deterministic policies.');
    }
    const seed = validateReliefAssignmentSeed(world, report.assignments, { previousAssignments });
    if (!seed.valid) throw new Error('Invalid negotiated incumbent.');
    const candidates = new Map(context.candidates.map(c => [c.id, c.assignment]));
    const findings = new Set(context.agentReports.flatMap(r => r.findings.map(f => f.id)));
    const requests = new Set(world.requests.map(r => r.id));
    const actors = new Set([...ROLES, 'supervisor']);
    const kinds = new Set(['cfp','proposal','accept','reject','bid','counterproposal','commit','defer','resolution']);
    const votes = new Map(), proposals = new Map(), committed = new Map(), deliveries = new Map();
    for (const [index, m] of report.messages.entries()) {
      if (m.id !== `SIM-NEG-${world.runId}-${world.revision}-${index + 1}` || !actors.has(m.from) || !actors.has(m.to) ||
          m.from === m.to || !kinds.has(m.kind) || !requests.has(m.requestId) || !Number.isInteger(m.round) ||
          m.round < 0 || m.round > settings.maxRounds || !Array.isArray(m.findingIds) || m.findingIds.some(id => !findings.has(id))) throw new Error('Invalid negotiation message.');
      if (m.candidateId) {
        const tuple = candidates.get(m.candidateId);
        if (!tuple || tuple.requestId !== m.requestId || !m.assignment || Object.keys(m.assignment).length !== 5 || !same(tuple, m.assignment)) throw new Error('Unknown negotiation candidate.');
      }
      if (m.candidateIds && (!Array.isArray(m.candidateIds) || m.candidateIds.length > 27 ||
          new Set(m.candidateIds).size !== m.candidateIds.length || m.candidateIds.some(id => candidates.get(id)?.requestId !== m.requestId))) throw new Error('Invalid negotiation bid.');
      if (m.kind === 'proposal') {
        if (m.from !== 'cargo' || !m.candidateId || m.proposalId !== `SIM-PROP-${world.runId}-${world.revision}-${m.requestId.slice(4)}-${m.round}`) throw new Error('Invalid negotiation proposal.');
        if (proposals.has(m.proposalId) && proposals.get(m.proposalId) !== m.candidateId) throw new Error('Conflicting proposal.');
        proposals.set(m.proposalId, m.candidateId);
      }
      if (['accept','reject'].includes(m.kind) && m.to === 'supervisor') {
        if (!ROLES.includes(m.from) || !m.candidateId || proposals.get(m.proposalId) !== m.candidateId) throw new Error('Vote without proposal.');
        const expected = localChecks(m.from, world, m.assignment, [...committed.values()]);
        if ((m.kind === 'accept') !== (expected.ruleCodes.length === 0) || JSON.stringify(m.ruleCodes) !== JSON.stringify(expected.ruleCodes)) throw new Error('Vote violates local constraints.');
        const prior = votes.get(m.proposalId) ?? new Map();
        if (prior.has(m.from)) throw new Error('Duplicate supervisor vote.');
        prior.set(m.from, m.kind); votes.set(m.proposalId, prior);
      }
      if (m.kind === 'commit') {
        if (m.from !== 'supervisor' || !ROLES.includes(m.to) || !m.candidateId || proposals.get(m.proposalId) !== m.candidateId ||
            !ROLES.every(role => votes.get(m.proposalId)?.get(role) === 'accept')) throw new Error('Commit without unanimous peer acceptance.');
        const recipients = deliveries.get(m.proposalId) ?? new Set();
        if (recipients.has(m.to)) throw new Error('Duplicate commitment delivery.');
        recipients.add(m.to); deliveries.set(m.proposalId, recipients);
        committed.set(m.proposalId, m.assignment);
      }
    }
    if ([...deliveries.values()].some(recipients => recipients.size !== ROLES.length) ||
        JSON.stringify(canonicalAssignments([...committed.values()])) !== JSON.stringify(canonicalAssignments(report.assignments))) throw new Error('Incomplete negotiated commitment.');
    if (['disabled','failed'].includes(report.status) && (report.messages.length || report.assignments.length)) throw new Error('Inactive negotiation cannot claim consensus.');
  } catch (error) { errors.push(error instanceof TypeError ? 'Invalid negotiation report.' : error.message); }
  return { valid: errors.length === 0, errors };
}

export function finishReliefNegotiation(report, world, plan, validation, { previousAssignments = report?.previousAssignments ?? [] } = {}) {
  if (!validateReliefNegotiationReport(world, report, { previousAssignments }).valid || validation?.valid !== true || !Array.isArray(validation.errors) || validation.errors.length) throw new TypeError('Negotiation resolution requires matching verified state.');
  const score = report.assignments.reduce((n, a) => n + world.requests.find(r => r.id === a.requestId).priority, 0);
  const retained = JSON.stringify(canonicalAssignments(report.assignments)) === JSON.stringify(canonicalAssignments(plan.assignments));
  const status = report.status === 'failed' ? 'deterministic-fallback' : report.status === 'disabled' ? 'disabled' : retained ? 'seed-retained' : 'solver-refined';
  return { ...report, outcome: { status, seedServedPriority: score, finalServedPriority: plan.objective.servedPriority, verified: true } };
}
