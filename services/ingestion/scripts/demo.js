import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { EVENT_TYPES } from '../src/contracts.js';
import { sampleEvent } from '../src/sample-events.js';

const base = new URL(process.env.INGESTION_DEMO_URL ?? 'http://127.0.0.1:3100');
if (!['http:', 'https:'].includes(base.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password) {
  throw new Error('Demo credentials may only be sent to a loopback API.');
}
const sources = JSON.parse(process.env.INGESTION_SOURCES_JSON ?? '[]');
if (!process.env.INGESTION_ADMIN_TOKEN || !sources.length) throw new Error('Generate and load .env credentials first.');
const request = async (path, body, token = process.env.INGESTION_ADMIN_TOKEN) => {
  const response = await fetch(new URL(path, base), { method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) });
  const result = await response.json();
  return { status: response.status, result };
};
let events;
if (process.argv.includes('--replay')) events = JSON.parse(readFileSync('var/demo-last.json', 'utf8'));
else {
  const now = Date.now();
  events = EVENT_TYPES.map((type) => {
    const source = sources.find((candidate) => candidate.types.includes(type));
    if (!source) throw new Error(`No configured demo source for ${type}.`);
    return sampleEvent(type, { sourceId: source.sourceId, now, sequence: now });
  });
  const changes = [
    { ...events[0], eventId: randomUUID(), sequence: now + 1, data: { ...events[0].data, status: 'maintenance' } },
    { ...events[1], eventId: randomUUID(), sequence: now + 1, data: { ...events[1].data, status: 'rest' } },
    { ...events[2], eventId: randomUUID(), sequence: now + 1, data: { ...events[2].data, condition: 'storm', windSpeedMps: 20, visibilityM: 1500 } },
    { ...events[3], eventId: randomUUID(), sequence: now + 1, data: { ...events[3].data, status: 'restricted', arrivalsPerHour: 2, departuresPerHour: 2 } },
  ];
  events.push(...changes, events[0], { ...events[0], eventId: randomUUID(), sequence: now - 1 },
    { ...events[2], eventId: randomUUID(), sequence: now - 1,
      observedAt: new Date(now - 60000).toISOString(), validUntil: new Date(now - 1000).toISOString() });
  mkdirSync('var', { recursive: true }); writeFileSync('var/demo-last.json', JSON.stringify(events, null, 2));
}
for (const input of events) {
  const source = sources.find((candidate) => candidate.sourceId === input.sourceId);
  if (!source) throw new Error('Saved scenario requires a matching configured source.');
  const response = await request('/v1/events', input, source.token);
  if (response.status >= 400) throw new Error(`Demo failed: ${response.result.error?.code ?? response.status}`);
  console.log(JSON.stringify({ type: input.type, status: response.status,
    disposition: response.result.disposition, duplicate: response.result.duplicate, delivery: response.result.delivery }));
}
const state = await request('/v1/state');
console.log(JSON.stringify({ latestEntities: state.result.items.length, states: state.result.items.map((item) => ({
  type: item.event.type, status: item.event.data.status ?? item.event.data.condition ?? item.event.data.category, freshness: item.freshness,
})) }));
const flush = await request('/v1/outbox/flush', {});
console.log(JSON.stringify({ brokerFlush: flush.status, ...flush.result }));
const metrics = await request('/v1/metrics'); console.log(JSON.stringify(metrics.result));
