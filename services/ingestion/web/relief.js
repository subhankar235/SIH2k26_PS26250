import { timestamp } from './format.js';

const get = (id) => document.getElementById(id);
const list = (value) => Array.isArray(value) ? value : [];
const value = (input) => typeof input === 'string' || (typeof input === 'number' && Number.isFinite(input)) ? String(input) : 'Not reported';
const labels = { fleet: 'Fleet', crew: 'Crew', weather: 'Weather', airport: 'Airport', cargo: 'Cargo' };
const phases = { 'weather-change': 'Weather change', 'maintenance-change': 'Maintenance change', 'airport-closure': 'Airport closure', 'new-request': 'New request', 'validity-expiry': 'Validity expiry', start: 'Initial scenario', 'gateway-update': 'Gateway update', 'input-expiry': 'Input expiry' };
function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = value(text);
  if (className) result.className = className;
  return result;
}
function section(title, note) {
  const result = node('section', undefined, 'relief-block');
  result.append(node('h3', title));
  if (note) result.append(node('p', note, 'muted small'));
  return result;
}
function definition(fields) {
  const result = node('dl', undefined, 'relief-definition');
  for (const [label, content] of fields) result.append(node('dt', label), node('dd', value(content)));
  return result;
}
function table(id, caption, headings, rows, empty) {
  if (!rows.length) {
    const fallback = node('p', empty, 'relief-empty');
    fallback.id = id; fallback.dataset.reliefTable = ''; fallback.tabIndex = -1;
    return fallback;
  }
  const scroll = node('div', undefined, 'table-scroll relief-table');
  scroll.id = id; scroll.dataset.reliefTable = '';
  scroll.tabIndex = 0; scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', `${caption}; scroll for more columns`);
  const result = node('table'); result.append(node('caption', caption, 'sr-only'));
  const head = node('thead'), header = node('tr'), body = node('tbody');
  for (const label of headings) { const cell = node('th', label); cell.scope = 'col'; header.append(cell); }
  head.append(header);
  for (const columns of rows) { const row = node('tr'); for (const content of columns) row.append(node('td', value(content))); body.append(row); }
  result.append(head, body); scroll.append(result); return scroll;
}
function joined(items) { return list(items).map(value).join(', ') || 'None'; }
function reportedTime(input) { return typeof input === 'string' ? timestamp(input) : 'Not reported'; }
function inputDetails(inputs) {
  const gateway = inputs.mode === 'gateway';
  const result = section(gateway ? 'Gateway inputs' : 'Scripted scenario inputs', gateway ? 'Only designated sources and known entities in this run namespace affect the fictional scenario. Input TTL follows wall-clock validity, independently of logical ticks.' : 'This run uses the fixed scripted scenario.');
  result.append(definition([['Input mode', gateway ? 'Gateway' : inputs.mode === 'scripted' ? 'Scripted' : value(inputs.mode)]]));
  if (!gateway) return result;
  result.append(definition([['Input namespace', inputs.namespace]]));
  const authorities = inputs.authorities && typeof inputs.authorities === 'object' && !Array.isArray(inputs.authorities) ? Object.entries(inputs.authorities) : [];
  result.append(table('relief-table-authorities', 'Gateway input authority', ['Fact type', 'Designated source'], authorities, 'No designated sources reported.'));
  result.append(table('relief-table-bindings', 'Gateway input bindings and validity', ['Fact type', 'Gateway entity / scenario entity', 'Source / event', 'Observed (UTC)', 'Valid until (UTC)', 'TTL state'], list(inputs.bindings).map((item) => [item.type, `${value(item.entityId)} / ${value(item.scenarioEntityId)}`, `${value(item.sourceId)} / ${value(item.eventId)}`, reportedTime(item.observedAt), reportedTime(item.validUntil), item.expired === true ? 'Expired' : item.expired === false ? 'Current' : 'Not reported']), 'No gateway facts bound to this run.'));
  return result;
}
function coordination(snapshot) {
  const result = section('Deterministic specialist coordination', 'Deterministic evidence exchange between bounded specialists and a supervisor. Messages describe constraint findings and a verified decision; they do not dispatch deliveries.');
  const exchange = snapshot.coordination;
  if (snapshot.planUsable === false || snapshot.inputFreshness?.replanPending === true) result.append(node('p', 'Retained coordination for the historical plan.', 'small relief-warning'));
  if (exchange.version !== 1 || exchange.topology !== 'specialists-supervisor') {
    result.append(node('p', 'Coordination format not supported by this viewer.', 'relief-empty')); return result;
  }
  const decision = exchange.decision;
  result.append(definition([['Topology', 'Specialists → Supervisor'], ['Decision status', decision?.status], ['Served priority', decision?.servedPriority], ['Assigned requests', decision?.assignedCount]]));
  const known = new Set(list(snapshot.plan.agentReports).flatMap((report) => list(report.findings).map((finding) => finding.id)));
  let omitted = false;
  const rows = list(exchange.messages).map((message) => {
    const ids = list(message.findingIds).filter((id) => known.has(id));
    if (ids.length !== list(message.findingIds).length) omitted = true;
    return [message.id, `${value(labels[message.from] || message.from)} → ${value(labels[message.to] || message.to)}`, message.kind, joined(message.entityIds), joined(ids), message.summary];
  });
  if (omitted) result.append(node('p', 'References outside the current specialist reports were omitted.', 'small relief-warning'));
  const details = node('details', undefined, 'relief-report relief-coordination'); details.dataset.reliefDetail = 'coordination';
  details.append(node('summary', `Inspect coordination messages · ${rows.length}`), table('relief-table-coordination', 'Deterministic coordination messages', ['Message ID', 'From → To', 'Kind', 'Entity IDs', 'Grounded finding IDs', 'Evidence summary'], rows, 'No coordination messages reported.'));
  result.append(details); return result;
}
const negotiationKinds = { cfp: 'Call for proposals', proposal: 'Proposal', accept: 'Acceptance', reject: 'Objection', bid: 'Bid', counterproposal: 'Counterproposal', commit: 'Commit', defer: 'Deferred request', resolution: 'Resolution' };
const negotiationStatuses = { agreed: 'Agreed', partial: 'Partial', no_agreement: 'No agreement', budget_exhausted: 'Budget exhausted', failed: 'Failed', disabled: 'Disabled', blocked: 'Blocked', deferred: 'Deferred' };
function negotiationReferences(snapshot) {
  const world = snapshot.world;
  const entities = new Set(['aircraft', 'crews', 'airports', 'requests'].flatMap((key) => list(world[key]).map((item) => item.id)));
  const requests = new Set(list(world.requests).map((item) => item.id));
  const aircraft = new Set(list(world.aircraft).map((item) => item.id)), crews = new Set(list(world.crews).map((item) => item.id));
  const knownFindings = new Set(list(snapshot.plan.agentReports).flatMap((report) => list(report.findings).map((finding) => finding.id)));
  const candidates = new Set();
  for (const request of list(world.requests)) for (const plane of aircraft) for (const crew of crews) for (const slot of list(world.policy?.slots)) {
    candidates.add(`SIM-CAND-${request.id.slice(4)}~${plane.slice(4)}~${crew.slice(4)}~${slot}~${slot + 1}`);
  }
  const candidateId = (assignment) => `SIM-CAND-${assignment.requestId.slice(4)}~${assignment.aircraftId.slice(4)}~${assignment.crewId.slice(4)}~${assignment.departureSlot}~${assignment.arrivalSlot}`;
  const assignmentKnown = (assignment) => assignment && Number.isInteger(assignment.departureSlot) && Number.isInteger(assignment.arrivalSlot) && requests.has(assignment.requestId) && aircraft.has(assignment.aircraftId) && crews.has(assignment.crewId) && candidates.has(candidateId(assignment));
  return { entities, requests, knownFindings, candidates, candidateId, assignmentKnown };
}
function negotiation(snapshot) {
  const historical = snapshot.planUsable === false || snapshot.inputFreshness?.replanPending === true;
  const result = section('Autonomous civilian negotiation', 'Deterministic policies make negotiation decisions through bounded contract-net proposals, objections and counterbids. No LLM makes these decisions. The independent checker remains authoritative; nothing is dispatched.');
  result.id = 'relief-negotiation';
  const report = snapshot.negotiation;
  if (report.runId !== snapshot.world.runId || report.revision !== snapshot.world.revision) {
    result.append(node('p', 'No negotiation report for this run and revision.', 'relief-empty')); return result;
  }
  if (report.version !== 1 || report.mode !== 'deterministic-autonomous' || report.topology !== 'fully-connected-peers') {
    result.append(node('p', 'Negotiation format not supported by this viewer.', 'relief-empty')); return result;
  }
  if (historical) result.append(node('p', 'Historical negotiation only. Retained activity, commitments and outcomes describe the prior input state; a verified replan is required.', 'relief-warning relief-label'));
  const refs = negotiationReferences(snapshot);
  let omitted = false;
  const grounded = (ids, known) => {
    const kept = list(ids).filter((id) => known.has(id));
    if (kept.length !== list(ids).length) omitted = true;
    return kept;
  };
  const actors = { ...labels, supervisor: 'Supervisor' };
  const messages = list(report.messages).filter((message) => {
    const valid = message && Object.hasOwn(actors, message.from) && Object.hasOwn(actors, message.to) && Object.hasOwn(negotiationKinds, message.kind) &&
      (!message.requestId || refs.requests.has(message.requestId)) && (!message.assignment || refs.assignmentKnown(message.assignment) && (!message.requestId || message.assignment.requestId === message.requestId)) &&
      (!message.candidateId || refs.candidates.has(message.candidateId)) && list(message.candidateIds).every((id) => refs.candidates.has(id)) &&
      (!message.assignment || !message.candidateId || refs.candidateId(message.assignment) === message.candidateId);
    if (!valid) omitted = true;
    return valid;
  });
  const proposals = new Set(messages.filter((message) => message.kind === 'proposal' && refs.requests.has(message.requestId) && message.candidateId && Number.isInteger(message.round) && message.round >= 1 && message.round <= 8 &&
    message.proposalId === `SIM-PROP-${report.runId}-${report.revision}-${message.requestId.slice(4)}-${message.round}`).map((message) => message.proposalId));
  const assignmentRows = (assignments) => list(assignments).filter((assignment) => {
    if (refs.assignmentKnown(assignment)) return true;
    omitted = true; return false;
  }).map((assignment) => [assignment.requestId, assignment.aircraftId, assignment.crewId, assignment.departureSlot, assignment.arrivalSlot]);
  result.append(definition([['Policy mode', 'Deterministic autonomous'], ['Topology', 'Fully connected peers and supervisor'], ['Negotiation status', negotiationStatuses[report.status] || 'Not reported'], ['Enabled', report.settings?.enabled === true ? 'Yes' : report.settings?.enabled === false ? 'No' : 'Not reported'], ['Rounds completed', report.roundsCompleted], ['Maximum rounds per request', report.settings?.maxRounds], ['Messages used / budget', `${list(report.messages).length} / ${value(report.settings?.maxMessages)}`]]));
  const outcome = report.outcome;
  const outcomeLabels = { 'seed-retained': 'Negotiated seed retained', 'solver-refined': 'Optimizer refined negotiated seed', 'deterministic-fallback': 'Deterministic optimizer fallback', disabled: 'Negotiation disabled' };
  if (outcome) {
    result.append(node('p', `${historical ? 'Historical outcome: ' : 'Outcome: '}${outcomeLabels[outcome.status] || 'Not reported'}`, 'relief-label'));
    result.append(definition([['Negotiated seed served priority', outcome.seedServedPriority], ['Optimizer final served priority', outcome.finalServedPriority], ['Outcome independently verified', outcome.verified === true ? 'Yes' : outcome.verified === false ? 'No' : 'Not reported']]));
  } else result.append(node('p', 'Negotiation outcome not reported.', 'relief-empty'));
  result.append(node('p', historical ? 'Historical negotiated seed' : 'Negotiated seed assignments', 'small relief-label'), table('relief-table-negotiation-seed', historical ? 'Historical negotiated seed' : 'Negotiated seed assignments', ['Request', 'Aircraft', 'Crew', 'Departure slot', 'Arrival slot'], assignmentRows(report.assignments), 'No negotiated assignments retained. Inspect request statuses and optimizer outcome.'));
  const requestRows = list(report.requests).filter((request) => {
    const valid = refs.requests.has(request?.requestId) && (!request.assignment || refs.assignmentKnown(request.assignment) && request.assignment.requestId === request.requestId);
    if (!valid) omitted = true;
    return valid;
  }).map((request) => [request.requestId, negotiationStatuses[request.status] || 'Not reported', request.rounds]);
  result.append(table('relief-table-negotiation-requests', 'Negotiation request results', ['Request', 'Status', 'Rounds'], requestRows, 'No request negotiation results reported.'));
  const agentRows = list(report.agentStates).filter((agent) => {
    if (agent && Object.hasOwn(labels, agent.agentId)) return true;
    omitted = true; return false;
  }).map((agent) => [labels[agent.agentId], joined(grounded(agent.acceptedProposalIds, proposals)), joined(grounded(agent.rejectedProposalIds, proposals)), agent.bidsSent]);
  result.append(table('relief-table-negotiation-agents', 'Negotiating agent activity', ['Policy actor', 'Accepted proposal IDs', 'Rejected proposal IDs', 'Bids sent'], agentRows, 'No agent activity reported.'));
  const messageRows = messages.filter((message) => {
    if (!message.proposalId || proposals.has(message.proposalId)) return true;
    omitted = true; return false;
  }).map((message) => [message.id, message.round, `${actors[message.from]} → ${actors[message.to]}`, negotiationKinds[message.kind], message.requestId || 'None', message.proposalId || 'None', joined(grounded(message.entityIds, refs.entities)), joined(grounded(message.findingIds, refs.knownFindings)), joined(message.ruleCodes), message.candidateId || joined(message.candidateIds), message.assignment ? `${message.assignment.aircraftId} / ${message.assignment.crewId} / ${message.assignment.departureSlot} → ${message.assignment.arrivalSlot}` : 'None', message.summary]);
  if (omitted) result.append(node('p', 'Unsupported or ungrounded references were omitted from this negotiation view.', 'small relief-warning'));
  const details = node('details', undefined, 'relief-report relief-coordination relief-negotiation-ledger'); details.dataset.reliefDetail = 'negotiation';
  details.append(node('summary', `Inspect ${historical ? 'historical ' : ''}peer negotiation messages · ${messageRows.length}`), table('relief-table-negotiation-messages', historical ? 'Historical peer negotiation messages' : 'Peer negotiation messages', ['Message ID', 'Round', 'From → To', 'Kind', 'Request', 'Proposal ID', 'Grounded entity IDs', 'Grounded finding IDs', 'Assignment rule codes', 'Candidate IDs', 'Candidate assignment', 'Policy summary'], messageRows, 'No supported negotiation messages reported.'));
  result.append(details); return result;
}
function weatherFeed(snapshot) {
  const result = section('Weather feed', 'Shows the most recent administrator-requested provider refresh. Monitor polling reads this status; it does not request live weather.');
  const feed = snapshot.weatherFeed;
  if (feed.runId !== snapshot.world.runId) {
    result.append(node('p', 'No weather feed result for this run.', 'relief-empty')); return result;
  }
  const state = ({ ready: 'Weather feed ready', degraded: 'Weather feed degraded', pending: 'Weather refresh pending' })[feed.status] || 'Weather feed state not reported';
  result.append(node('p', state, `relief-label${feed.status === 'degraded' ? ' relief-warning' : ''}`));
  if (feed.revision !== snapshot.world.revision) result.append(node('p', 'Feed result from earlier revision. Inspect its timestamp and binding TTL before interpreting current scenario weather.', 'small relief-warning'));
  result.append(definition([['Feed revision', feed.revision], ['Command', feed.commandId], ['Scenario airport', feed.airportId], ['Provider location', feed.location], ['Feed updated', reportedTime(feed.generatedAt)]]));
  if (feed.status === 'pending') result.append(node('p', 'Awaiting a provider response. Current scenario inputs remain in effect.', 'small'));
  if (feed.status === 'degraded') result.append(node('p', `Refresh failed: ${value(feed.errorCode)}. This attempt did not replace scenario weather.`, 'small relief-warning'));
  if (feed.provenance && typeof feed.provenance === 'object') {
    const source = feed.provenance;
    result.append(definition([['Provider', source.provider], ['Provenance location', source.location], ['Latitude / longitude', `${value(source.latitude)} / ${value(source.longitude)}`], ['Fetched', reportedTime(source.fetchedAt)], ['Weather observation', reportedTime(source.weatherTime)], ['Visibility observation', reportedTime(source.visibilityTime)]]));
  } else result.append(node('p', 'Provider provenance not reported for this attempt.', 'relief-empty'));
  return result;
}
function annotationLabel(status) {
  return ({ deterministic: 'Deterministic evidence selection', model: 'Local LLM evidence selection', 'deterministic-fallback': 'Deterministic fallback', disabled: 'Annotation disabled', pending: 'Annotation pending' })[status] || value(status);
}
function matchingAnnotations(snapshot) {
  const annotation = snapshot.annotations;
  return annotation?.runId === snapshot.world.runId && annotation?.revision === snapshot.world.revision ? annotation : null;
}
function annotations(snapshot) {
  const result = section('Evidence annotations', 'Evidence selection only. Specialist findings and the independent checker remain authoritative for this fictional scenario.');
  const annotation = matchingAnnotations(snapshot);
  if (!annotation) { result.append(node('p', 'Awaiting annotations for this revision.', 'relief-empty')); return result; }
  const state = ({ pending: 'Annotation pending', disabled: 'Annotation disabled', degraded: 'Deterministic fallback / degraded annotation', ready: 'Annotation ready' })[annotation.status] || 'Annotation state not reported';
  result.append(node('p', state, 'relief-label'));
  if (annotation.mode) result.append(node('p', annotation.mode === 'ollama' ? 'Provider: local Ollama LLM' : annotation.mode === 'deterministic' ? 'Provider: deterministic rules' : annotation.mode === 'deterministic-fallback' ? 'Provider: deterministic fallback after local model failure' : 'Provider: not reported', 'small'));
  if (Array.isArray(annotation.modelsUsed)) result.append(node('p', `Successful local models used: ${joined(annotation.modelsUsed)}`, 'small mono'));
  for (const highlight of list(annotation.highlights)) {
    if (!labels[highlight.agentId]) continue;
    const report = list(snapshot.plan.agentReports).find((item) => item.agentId === highlight.agentId);
    const known = new Set(list(report?.findings).map((finding) => finding.id));
    const ids = list(highlight.findingIds).filter((id) => known.has(id));
    const line = node('p', `${labels[highlight.agentId]}: ${annotationLabel(highlight.status)}${highlight.model ? ` · Model: ${value(highlight.model)}` : ''}`, 'small');
    line.append(node('span', `Evidence finding IDs: ${joined(ids)}`, 'cell-secondary mono')); result.append(line);
  }
  if (annotation.generatedAt) result.append(node('p', `Annotated: ${timestamp(annotation.generatedAt)}`, 'muted small'));
  return result;
}
function reports(snapshot) {
  const result = section('Specialist reports', 'All findings are shown, including those not selected by annotations. These are bounded constraint specialists, not autonomous operators.');
  const annotation = matchingAnnotations(snapshot);
  for (const [agentId, label] of Object.entries(labels)) {
    const report = list(snapshot.plan.agentReports).find((item) => item.agentId === agentId);
    const details = node('details', undefined, 'relief-report'); details.dataset.reliefDetail = agentId;
    const findings = list(report?.findings);
    details.append(node('summary', `${label} · ${findings.length} ${findings.length === 1 ? 'finding' : 'findings'}`));
    if (!report) details.append(node('p', 'Report not available.', 'relief-empty'));
    else {
      details.append(node('p', `Eligible IDs: ${joined(report.eligibleIds)}`, 'small mono'));
      const selected = new Set(list(annotation?.highlights).filter((item) => item.agentId === agentId).flatMap((item) => list(item.findingIds)));
      const findingList = node('ul', undefined, 'relief-findings');
      for (const finding of findings) {
        const item = node('li');
        item.append(node('p', `${value(finding.id)} · ${value(finding.code)}${selected.has(finding.id) ? ' · Selected evidence' : ''}`, 'mono relief-label'), node('p', finding.message), node('p', `Entity IDs: ${joined(finding.entityIds)}`, 'muted small mono'));
        findingList.append(item);
      }
      details.append(findings.length ? findingList : node('p', 'No findings reported.', 'relief-empty'));
    }
    result.append(details);
  }
  return result;
}
function worldDetails(world) {
  const details = node('details', undefined, 'relief-world relief-report'); details.dataset.reliefDetail = 'world';
  details.append(node('summary', 'Inspect fictional world and scenario metadata'));
  details.append(node('p', `Departure slots: ${joined(world.policy?.slots)} · ${value(world.policy?.slotMinutes)} logical minutes per slot. Scenario limits: visibility at least ${value(world.policy?.minVisibilityM)} m; wind at most ${value(world.policy?.maxWindSpeedMps)} m/s. These fixed educational limits are not aviation guidance.`, 'muted small'));
  details.append(table('relief-table-aircraft', 'Fictional aircraft', ['Aircraft', 'Airport', 'Capacity (kg)', 'Cold storage', 'Status', 'Valid through tick'], list(world.aircraft).map((item) => [item.id,item.airportId,item.capacityKg,item.coldStorage === true ? 'Yes' : 'No',item.status,item.validThroughTick]), 'No aircraft reported.'));
  details.append(table('relief-table-crews', 'Fictional crews', ['Crew', 'Status', 'Qualifications', 'From slot', 'Through slot', 'Valid through tick'], list(world.crews).map((item) => [item.id,item.status,joined(item.qualifications),item.fromSlot,item.toSlot,item.validThroughTick]), 'No crews reported.'));
  details.append(table('relief-table-airports', 'Fictional airports', ['Airport', 'Status', 'Arrivals / slot', 'Departures / slot', 'Valid through tick'], list(world.airports).map((item) => [item.id,item.status,item.arrivalsPerSlot,item.departuresPerSlot,item.validThroughTick]), 'No airports reported.'));
  details.append(table('relief-table-weather', 'Fictional weather', ['Airport', 'Condition', 'Wind (m/s)', 'Visibility (m)', 'Valid through tick'], list(world.weather).map((item) => [item.airportId,item.condition,item.windSpeedMps,item.visibilityM,item.validThroughTick]), 'No weather reported.'));
  details.append(table('relief-table-routes', 'Fictional routes', ['Origin', 'Destination', 'Duration (slots)'], list(world.routes).map((item) => [item.originId,item.destinationId,item.durationSlots]), 'No routes reported.'));
  return details;
}
export function reliefClear() {
  const hadFocus = get('relief-content').contains(document.activeElement);
  get('relief-content').replaceChildren(); get('relief-state').textContent = '';
  if (hadFocus) { get('relief-title').tabIndex = -1; get('relief-title').focus({ preventScroll: true }); }
}
export function reliefUnavailable(unimplemented = false) {
  reliefClear();
  get('relief-state').textContent = unimplemented ? 'Simulation view is not available on this gateway yet. Reported facts remain available.' : 'Simulation unavailable. Retrying with the next monitor refresh.';
}
export function reliefRender(snapshot) {
  if (snapshot?.status === 'idle') { reliefClear(); get('relief-state').textContent = 'No simulation has been started. This viewer is read only.'; return; }
  if (snapshot?.status !== 'ready' || snapshot.world?.simulation !== true || !snapshot.plan || !snapshot.validation) throw new Error('Invalid simulation snapshot');
  const content = get('relief-content');
  const open = new Set([...content.querySelectorAll('details[open]')].map((item) => item.dataset.reliefDetail));
  const focusedTable = document.activeElement?.closest('[data-relief-table]')?.id;
  const focusedDetail = document.activeElement?.closest('[data-relief-detail]')?.dataset.reliefDetail;
  const scrollPositions = new Map([...content.querySelectorAll('[data-relief-table]')].map((item) => [item.id, { left: item.scrollLeft, top: item.scrollTop }]));
  const { world, plan, validation, demand } = snapshot;
  const historical = snapshot.planUsable === false || snapshot.inputFreshness?.replanPending === true;
  const revision = section('Current revision');
  revision.append(definition([['Run', world.runId], ['Revision / logical tick', `${value(world.revision)} / ${value(world.tick)}`], ['Next fixed phase', snapshot.inputs?.mode === 'gateway' ? 'Gateway events and input expiry' : snapshot.nextPhase === null ? 'Scenario complete' : phases[snapshot.nextPhase] || value(snapshot.nextPhase)], ['Snapshot generated', timestamp(snapshot.generatedAt)]]));
  if (snapshot.inputFreshness) {
    revision.append(definition([['Input freshness', snapshot.inputFreshness.status], ['Expired bindings', snapshot.inputFreshness.expiredCount]]));
    revision.append(node('p', snapshot.inputFreshness.replanPending === true ? 'Expiry replan pending' : 'Expiry replan not pending', 'small'));
  }
  if (historical) revision.append(node('p', 'Historical plan only. Input validity has changed; this plan is unavailable as a current proposal until a verified replan completes.', 'relief-label relief-warning'));
  const proposal = section(historical ? 'Historical assignments' : 'Proposed assignments', historical ? 'Retained assignments for inspection of the prior input state.' : 'Read-only proposals in a toy horizon. Nothing is dispatched or executed.');
  const status = plan.status === 'optimal' ? 'Exact optimum within the bounded scenario' : plan.status === 'feasible_budget' ? 'Budget-limited feasible result · Optimality not established' : 'Planner status not reported';
  proposal.append(node('p', historical ? `Historical search result: ${status}` : status, 'relief-label'));
  proposal.append(definition([['Served priority', plan.objective?.servedPriority], ['Changed surviving assignments', plan.objective?.changedAssignments], ['Total arrival slots', plan.objective?.totalArrivalSlots], ['Search nodes explored / limit', `${value(plan.diagnostics?.nodesExplored)} / ${value(plan.diagnostics?.nodeLimit)}`]]));
  proposal.append(table('relief-table-assignments', historical ? 'Historical relief assignments' : 'Proposed relief assignments', ['Request', 'Aircraft', 'Crew', 'Departure slot', 'Arrival slot'], list(plan.assignments).map((item) => [item.requestId,item.aircraftId,item.crewId,item.departureSlot,item.arrivalSlot]), historical ? 'No assignments retained for this historical input state.' : 'No feasible assignments proposed. Review unmet requests and specialist findings.'));
  const unmet = section('Unmet requests');
  unmet.append(table('relief-table-unmet', 'Unmet relief requests', ['Request', 'Reason codes'], list(plan.unserved).map((item) => [item.requestId, joined(item.reasonCodes)]), 'No unmet requests in this plan.'));
  const checker = section('Independent checker', 'Checks IDs, resource use, hard constraints and the reported objective independently of the search.');
  checker.append(node('p', validation.valid === true ? historical ? 'Passed for the retained input state. Current inputs require a verified replan.' : 'Passed · Plan satisfies the fictional scenario constraints' : 'Failed · Do not treat this proposal as a valid scenario plan', `relief-label ${validation.valid === true && !historical ? 'relief-pass' : 'relief-warning'}`));
  for (const error of list(validation.errors)) checker.append(node('p', error, 'small mono relief-warning'));
  const forecast = section('Synthetic demand forecast', 'Trained and evaluated on seeded synthetic data only. It does not create requests or change hard constraints; no real-world accuracy claim.');
  forecast.append(definition([['Model', demand?.modelId], ['Synthetic day', demand?.forecastDay], ['Predicted request count', demand?.predictedRequests], ['Training / held-out samples', `${value(demand?.trainingCount)} / ${value(demand?.testCount)}`], ['Held-out MAE / baseline MAE', `${value(demand?.evaluation?.mae)} / ${value(demand?.evaluation?.baselineMae)}`]]));
  const requests = section('Fictional relief requests', 'Priority, cold storage and logical validity are scenario metadata.');
  requests.append(table('relief-table-requests', 'Fictional request metadata', ['Request / category', 'Route', 'Mass (kg)', 'Priority', 'Cold chain', 'Deadline slot', 'Valid through tick'], list(world.requests).map((item) => [`${value(item.id)} / ${value(item.category)}`,`${value(item.originId)} → ${value(item.destinationId)}`,item.massKg,item.priority,item.temperatureControlled === true ? 'Required' : 'No',item.deadlineSlot,item.validThroughTick]), 'No fictional requests reported.'));
  const history = section('Prior revisions', 'Current run only. Up to 21 retained revision summaries in a gateway run; six in the scripted demo.');
  history.append(table('relief-table-history', 'Relief revision history', ['Revision', 'Phase', 'Served priority', 'Assignments', 'Changed assignments'], list(snapshot.history).map((item) => [item.revision,phases[item.phase] || item.phase,item.servedPriority,item.assignedCount,item.changedAssignments]), 'No prior revisions reported.'));
  const overview = node('div', undefined, 'relief-overview'); overview.append(revision, checker, forecast);
  const inputSections = [];
  if (snapshot.inputs) inputSections.push(inputDetails(snapshot.inputs));
  if (snapshot.weatherFeed) inputSections.push(weatherFeed(snapshot));
  if (snapshot.coordination) inputSections.push(coordination(snapshot));
  if (snapshot.negotiation) inputSections.push(negotiation(snapshot));
  content.replaceChildren(overview, ...inputSections, proposal, unmet, requests, worldDetails(world), annotations(snapshot), reports(snapshot), history);
  get('relief-state').textContent = `Revision ${value(world.revision)} · Logical tick ${value(world.tick)} · Fictional scenario`;
  for (const details of content.querySelectorAll('[data-relief-detail]')) {
    details.open = open.has(details.dataset.reliefDetail);
    if (!focusedTable && details.dataset.reliefDetail === focusedDetail) details.querySelector('summary').focus({ preventScroll: true });
  }
  for (const region of content.querySelectorAll('[data-relief-table]')) {
    const position = scrollPositions.get(region.id);
    if (position) { region.scrollLeft = position.left; region.scrollTop = position.top; }
  }
  if (focusedTable && get(focusedTable)) get(focusedTable).focus({ preventScroll: true });
  else if (focusedTable || (focusedDetail && ![...content.querySelectorAll('[data-relief-detail]')].some((details) => details.dataset.reliefDetail === focusedDetail))) {
    get('relief-title').tabIndex = -1; get('relief-title').focus({ preventScroll: true });
  }
}
