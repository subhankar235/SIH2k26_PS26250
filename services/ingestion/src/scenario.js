import { randomUUID } from 'node:crypto';
import { EVENT_TYPES } from './contracts.js';
import { sampleEvent } from './sample-events.js';

/** A finite fictional fact-update scenario, without flight plans or decisions. */
export function buildScenario({ sources, now = Date.now(), intervalMs = 5000, runId = randomUUID().slice(0, 8) }) {
  if (!Number.isInteger(intervalMs) || intervalMs < 100 || intervalMs > 10000 || !/^[A-Za-z0-9_-]{1,16}$/.test(runId)) throw new Error('Invalid scenario bounds.');
  const events = EVENT_TYPES.map((type) => {
    const source = sources.find((s) => s.types.includes(type));
    if (!source) throw new Error(`No configured scenario source for ${type}.`);
    return { ...sampleEvent(type, { sourceId: source.sourceId, now, entityId: `fixture-${runId}-${type.split('.')[0]}` }),
      validUntil: new Date(now + 120000).toISOString() };
  });
  const changed = (index, sequence, data) => ({ ...events[index], eventId: randomUUID(), sequence, data: { ...events[index].data, ...data } });
  const weather = changed(2, 2, { condition: 'rain', windSpeedMps: 12, visibilityM: 3000 });
  const maintenance = changed(0, 3, { status: 'maintenance', maintenanceDueAt: new Date(now - 60000).toISOString() });
  const capacity = changed(3, 2, { status: 'closed', arrivalsPerHour: 0, departuresPerHour: 0 });
  const shortLived = { ...changed(1, 2, { status: 'rest' }), validUntil: new Date(now + intervalMs * 6).toISOString() };
  return { version: 1, runId, createdAt: new Date(now).toISOString(), steps: [
    { label: 'Fictional starting observations', delayMs: 0, events },
    { label: 'Weather observation changes', delayMs: intervalMs, events: [weather] },
    { label: 'Maintenance report and sequence-gap indicator', delayMs: intervalMs, events: [maintenance] },
    { label: 'Airport reports temporary closure', delayMs: intervalMs, events: [capacity] },
    { label: 'Duplicate replay and stale assertion preserved in history', delayMs: intervalMs, events: [weather, changed(0, 2, { status: 'available' })] },
    { label: 'Crew assertion with short validity', delayMs: intervalMs, events: [shortLived] },
    { label: 'Validity expires; monitor must stop labelling that assertion current', delayMs: intervalMs * 2, events: [] },
  ] };
}
