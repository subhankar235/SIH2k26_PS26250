import { age, timestamp, typeLabels, flagLabels, reportedValue, safeRecord } from './format.js';

export const element = (id) => document.getElementById(id);
function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}
function badge(text, review) { return node('span', text, `badge ${review ? 'review' : 'current'}`); }

export function connection(message, stale = false, generatedAt = null) {
  element('connection-text').textContent = message;
  element('connection').classList.toggle('stale', stale);
  element('snapshot-time').textContent = generatedAt ? `Snapshot: ${timestamp(generatedAt)}` : '';
}
export function summary(snapshot) {
  const metrics = [['Selected records', 'total', ''], ['Current', 'current', 'current'],
    ['Expired', 'expired', 'review'], ['Sequence gaps', 'sequenceGaps', 'review'], ['Disagreements', 'disagreements', 'review']];
  element('summary').replaceChildren(...metrics.map(([label, key, tone]) => {
    const metric = node('div', undefined, `metric ${tone}`);
    metric.append(node('div', snapshot.summary[key] ?? 0, 'metric-value'), node('div', label, 'metric-label'));
    return metric;
  }));
  element('scope-note').textContent = `${snapshot.scope.shown.toLocaleString()} selected records · limit ${snapshot.scope.limit.toLocaleString()}${snapshot.scope.truncated ? ' · More records exist; narrow your filters.' : ' · All selected records shown.'}`;
  const delivery = [];
  for (const [key, label] of [['queued', 'Queued'], ['dead', 'Failed / dead'], ['published', 'Published']]) {
    delivery.push(node('dt', label), node('dd', snapshot.delivery[key] ?? 0));
  }
  element('delivery').replaceChildren(...delivery);
}

export function table(snapshot, page, pageSize, onInspect) {
  const records = snapshot.records.slice(page * pageSize, (page + 1) * pageSize);
  const focusedRecord = document.activeElement?.dataset?.inspectionId;
  element('records').replaceChildren(...records.map((record) => {
    const row = node('tr'); const event = record.event;
    const entity = node('td');
    entity.append(node('div', event.entityId, 'entity mono'), node('span', typeLabels[event.type] || event.type, 'cell-secondary'));
    const source = node('td', event.sourceId, 'mono');
    const value = node('td', reportedValue(record));
    const freshness = node('td');
    freshness.append(badge(record.freshness === 'current' ? 'Current' : 'Expired', record.freshness !== 'current'), node('span', age(record.ageMs), 'cell-secondary'));
    freshness.title = `Observed: ${timestamp(event.observedAt)}; valid until: ${timestamp(event.validUntil)}`;
    const quality = node('td'); const flags = node('div', undefined, 'flags');
    if (!record.flags.length) flags.append(node('span', 'No flags', 'muted'));
    for (const flag of record.flags) flags.append(badge(flagLabels[flag] || flag, true));
    quality.append(flags);
    const action = node('td'); const inspect = node('button', 'Inspect', 'secondary inspect-button');
    inspect.dataset.inspectionId = event.eventId;
    inspect.setAttribute('aria-label', `Inspect ${event.entityId} from ${event.sourceId}`);
    inspect.addEventListener('click', () => onInspect(record)); action.append(inspect);
    row.append(entity, source, value, freshness, quality, action); return row;
  }));
  element('table-state').hidden = records.length > 0;
  element('table-state').textContent = 'No reports match these filters. Try another source or clear the filters.';
  const total = snapshot.records.length;
  element('page-description').textContent = total ? `${page * pageSize + 1}–${Math.min(total, (page + 1) * pageSize)} of ${total} · Page ${page + 1} of ${Math.ceil(total / pageSize)}` : '0 records';
  element('previous').disabled = page === 0;
  element('next').disabled = (page + 1) * pageSize >= total;
  if (focusedRecord) restoreInspectionFocus(focusedRecord);
}

export function restoreInspectionFocus(eventId) {
  const button = Array.from(element('records').querySelectorAll('button')).find((item) => item.dataset.inspectionId === eventId);
  (button || document.querySelector('.table-scroll')).focus();
}

export function inspector(record, generatedAt) {
  const event = record.event;
  element('inspector').dataset.inspectionId = event.eventId;
  element('inspector-title').textContent = event.entityId;
  const details = node('dl', undefined, 'provenance');
  const fields = [
    ['Fact type', typeLabels[event.type] || event.type], ['Source ID', event.sourceId], ['Event ID', event.eventId],
    ['Sequence', event.sequence], ['Gateway cursor', record.cursor], ['Observed at', timestamp(event.observedAt)],
    ['Valid until', timestamp(event.validUntil)], ['Received at', timestamp(record.receivedAt)],
    ['Snapshot at', timestamp(generatedAt)], ['Freshness at snapshot', record.freshness],
    ['Age at snapshot', age(record.ageMs)], ['Reported status', record.reportedStatus ?? 'Not reported'],
    ['Quality flags', record.flags.map((flag) => flagLabels[flag] || flag).join(', ') || 'None'],
    ['Ingestion disposition', record.disposition], ['Delivery at snapshot', record.delivery],
  ];
  for (const [label, value] of fields) details.append(node('dt', label), node('dd', value, 'mono'));
  const content = element('inspector-content');
  content.replaceChildren(details, node('h3', 'Reported payload'), node('pre', JSON.stringify(safeRecord(record).event.data, null, 2)));
  element('inspector').showModal(); element('close-inspector').focus();
}

export function clearInspector() {
  element('inspector-content').replaceChildren();
  element('inspector-title').textContent = 'Record details';
  delete element('inspector').dataset.inspectionId;
}

export function clearData() {
  if (element('inspector').open) element('inspector').close();
  clearInspector();
  element('summary').replaceChildren(); element('records').replaceChildren(); element('delivery').replaceChildren();
  element('scope-note').textContent = 'No snapshot loaded'; element('snapshot-time').textContent = '';
  element('table-state').hidden = false; element('table-state').textContent = 'Loading source reports…';
  element('page-description').textContent = 'No records loaded';
  for (const id of ['previous', 'next', 'download']) element(id).disabled = true;
}
