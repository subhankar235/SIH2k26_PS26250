export const typeLabels = {
  'aircraft.status': 'Aircraft status', 'crew.availability': 'Crew availability',
  'weather.observation': 'Weather observation', 'airport.capacity': 'Airport capacity',
  'cargo.request': 'Cargo request',
};
export const flagLabels = {
  expired: 'Expired', sequence_gap: 'Sequence gap', source_disagreement: 'Source disagreement',
  maintenance_date_passed: 'Maintenance date passed',
};
export function timestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not reported' : `${date.toISOString().replace('T', ' ').slice(0, 19)} UTC`;
}
export function age(ms) {
  if (!Number.isFinite(ms)) return 'Age unknown';
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s old`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m old`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h old`;
  return `${Math.floor(ms / 86_400_000)}d old`;
}
export function reportedValue(record) {
  if (record.reportedStatus !== null && record.reportedStatus !== undefined) return record.reportedStatus;
  const { type, data } = record.event;
  if (type === 'weather.observation') return `${data.condition} · ${data.temperatureC} °C`;
  if (type === 'cargo.request') return `${data.category} · ${data.massKg} kg`;
  return 'Not reported';
}

// Export only the documented event contract; never serialize an arbitrary API response.
const dataKeys = {
  'aircraft.status': ['status', 'airportId', 'capacityKg', 'maintenanceDueAt'],
  'crew.availability': ['status', 'qualifications', 'availableFrom', 'availableUntil'],
  'weather.observation': ['temperatureC', 'windSpeedMps', 'visibilityM', 'condition'],
  'airport.capacity': ['status', 'arrivalsPerHour', 'departuresPerHour'],
  'cargo.request': ['category', 'massKg', 'originAirportId', 'destinationAirportId', 'requestedDeliveryBy', 'temperatureControlled'],
};
function pick(value, keys) {
  return Object.fromEntries(keys.filter((key) => value[key] !== undefined).map((key) => [key, value[key]]));
}
export function safeRecord(record) {
  const event = pick(record.event, ['schemaVersion', 'eventId', 'sourceId', 'entityId', 'type', 'sequence', 'observedAt', 'validUntil']);
  event.data = pick(record.event.data, dataKeys[event.type] || []);
  return { ...pick(record, ['eventId', 'cursor', 'disposition', 'duplicate', 'delivery', 'warnings', 'receivedAt', 'freshness', 'ageMs', 'flags', 'reportedStatus']), event };
}
export function safeSnapshot(snapshot) {
  return {
    generatedAt: snapshot.generatedAt,
    scope: pick(snapshot.scope, ['limit', 'shown', 'truncated']),
    summary: { ...pick(snapshot.summary, ['total', 'current', 'expired', 'sequenceGaps', 'disagreements']),
      byType: pick(snapshot.summary.byType || {}, Object.keys(typeLabels)) },
    records: snapshot.records.map(safeRecord),
    delivery: pick(snapshot.delivery, ['queued', 'dead', 'published']),
    deliveryScope: 'global_outbox',
  };
}
