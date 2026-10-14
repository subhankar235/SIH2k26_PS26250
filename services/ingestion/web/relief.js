import { timestamp } from './format.js';

const get = (id) => document.getElementById(id);
const list = (value) => Array.isArray(value) ? value : [];
const value = (input) => typeof input === 'string' || (typeof input === 'number' && Number.isFinite(input)) ? String(input) : 'Not reported';
const labels = { fleet: 'Fleet', crew: 'Crew', weather: 'Weather', airport: 'Airport', cargo: 'Cargo' };
const phases = { 'weather-change': 'Weather change', 'maintenance-change': 'Maintenance change', 'airport-closure': 'Airport closure', 'new-request': 'New request', 'validity-expiry': 'Validity expiry', start: 'Initial scenario' };
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
function table(caption, headings, rows, empty) {
  if (!rows.length) return node('p', empty, 'relief-empty');
  const scroll = node('div', undefined, 'table-scroll relief-table');
  scroll.tabIndex = 0; scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', `${caption}; scroll for more columns`);
  const result = node('table'); result.append(node('caption', caption, 'sr-only'));
  const head = node('thead'), header = node('tr'), body = node('tbody');
  for (const label of headings) { const cell = node('th', label); cell.scope = 'col'; header.append(cell); }
  head.append(header);
  for (const columns of rows) { const row = node('tr'); for (const content of columns) row.append(node('td', value(content))); body.append(row); }
  result.append(head, body); scroll.append(result); return scroll;
}
function joined(items) { return list(items).map(value).join(', ') || 'None'; }
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
  details.append(table('Fictional aircraft', ['Aircraft', 'Airport', 'Capacity (kg)', 'Cold storage', 'Status', 'Valid through tick'], list(world.aircraft).map((item) => [item.id,item.airportId,item.capacityKg,item.coldStorage === true ? 'Yes' : 'No',item.status,item.validThroughTick]), 'No aircraft reported.'));
  details.append(table('Fictional crews', ['Crew', 'Status', 'Qualifications', 'From slot', 'Through slot', 'Valid through tick'], list(world.crews).map((item) => [item.id,item.status,joined(item.qualifications),item.fromSlot,item.toSlot,item.validThroughTick]), 'No crews reported.'));
  details.append(table('Fictional airports', ['Airport', 'Status', 'Arrivals / slot', 'Departures / slot', 'Valid through tick'], list(world.airports).map((item) => [item.id,item.status,item.arrivalsPerSlot,item.departuresPerSlot,item.validThroughTick]), 'No airports reported.'));
  details.append(table('Fictional weather', ['Airport', 'Condition', 'Wind (m/s)', 'Visibility (m)', 'Valid through tick'], list(world.weather).map((item) => [item.airportId,item.condition,item.windSpeedMps,item.visibilityM,item.validThroughTick]), 'No weather reported.'));
  details.append(table('Fictional routes', ['Origin', 'Destination', 'Duration (slots)'], list(world.routes).map((item) => [item.originId,item.destinationId,item.durationSlots]), 'No routes reported.'));
  return details;
}
export function reliefClear() {
  get('relief-content').replaceChildren(); get('relief-state').textContent = '';
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
  const focused = document.activeElement?.closest('[data-relief-detail]')?.dataset.reliefDetail;
  const { world, plan, validation, demand } = snapshot;
  const revision = section('Current revision');
  revision.append(definition([['Run', world.runId], ['Revision / logical tick', `${value(world.revision)} / ${value(world.tick)}`], ['Next fixed phase', snapshot.nextPhase === null ? 'Scenario complete' : phases[snapshot.nextPhase] || value(snapshot.nextPhase)], ['Snapshot generated', timestamp(snapshot.generatedAt)]]));
  const proposal = section('Proposed assignments', 'Read-only proposals in a toy horizon. Nothing is dispatched or executed.');
  const status = plan.status === 'optimal' ? 'Exact optimum within the bounded scenario' : plan.status === 'feasible_budget' ? 'Budget-limited feasible result · Optimality not established' : 'Planner status not reported';
  proposal.append(node('p', status, 'relief-label'));
  proposal.append(definition([['Served priority', plan.objective?.servedPriority], ['Changed surviving assignments', plan.objective?.changedAssignments], ['Total arrival slots', plan.objective?.totalArrivalSlots], ['Search nodes explored / limit', `${value(plan.diagnostics?.explored)} / ${value(plan.diagnostics?.limit)}`]]));
  proposal.append(table('Proposed relief assignments', ['Request', 'Aircraft', 'Crew', 'Departure slot', 'Arrival slot'], list(plan.assignments).map((item) => [item.requestId,item.aircraftId,item.crewId,item.departureSlot,item.arrivalSlot]), 'No feasible assignments proposed. Review unmet requests and specialist findings.'));
  const unmet = section('Unmet requests');
  unmet.append(table('Unmet relief requests', ['Request', 'Reason codes'], list(plan.unserved).map((item) => [item.requestId, joined(item.reasonCodes)]), 'No unmet requests in this plan.'));
  const checker = section('Independent checker', 'Checks IDs, resource use, hard constraints and the reported objective independently of the search.');
  checker.append(node('p', validation.valid === true ? 'Passed · Plan satisfies the fictional scenario constraints' : 'Failed · Do not treat this proposal as a valid scenario plan', `relief-label ${validation.valid === true ? 'relief-pass' : 'relief-warning'}`));
  for (const error of list(validation.errors)) checker.append(node('p', error, 'small mono relief-warning'));
  const forecast = section('Synthetic demand forecast', 'Trained and evaluated on seeded synthetic data only. It does not create requests or change hard constraints; no real-world accuracy claim.');
  forecast.append(definition([['Model', demand?.modelId], ['Synthetic day', demand?.forecastDay], ['Predicted request count', demand?.predictedRequests], ['Training / held-out samples', `${value(demand?.trainingCount)} / ${value(demand?.testCount)}`], ['Held-out MAE / baseline MAE', `${value(demand?.evaluation?.mae)} / ${value(demand?.evaluation?.baselineMae)}`]]));
  const requests = section('Fictional relief requests', 'Priority, cold storage and logical validity are scenario metadata.');
  requests.append(table('Fictional request metadata', ['Request / category', 'Route', 'Mass (kg)', 'Priority', 'Cold chain', 'Deadline slot', 'Valid through tick'], list(world.requests).map((item) => [`${value(item.id)} / ${value(item.category)}`,`${value(item.originId)} → ${value(item.destinationId)}`,item.massKg,item.priority,item.temperatureControlled === true ? 'Required' : 'No',item.deadlineSlot,item.validThroughTick]), 'No fictional requests reported.'));
  const history = section('Prior revisions', 'Current run only. Up to six retained revision summaries.');
  history.append(table('Relief revision history', ['Revision', 'Phase', 'Served priority', 'Assignments', 'Changed assignments'], list(snapshot.history).map((item) => [item.revision,phases[item.phase] || item.phase,item.servedPriority,item.assignedCount,item.changedAssignments]), 'No prior revisions reported.'));
  const overview = node('div', undefined, 'relief-overview'); overview.append(revision, checker, forecast);
  content.replaceChildren(overview, proposal, unmet, requests, worldDetails(world), annotations(snapshot), reports(snapshot), history);
  get('relief-state').textContent = `Revision ${value(world.revision)} · Logical tick ${value(world.tick)} · Fictional scenario`;
  for (const details of content.querySelectorAll('[data-relief-detail]')) {
    details.open = open.has(details.dataset.reliefDetail);
    if (details.dataset.reliefDetail === focused) details.querySelector('summary').focus();
  }
}
