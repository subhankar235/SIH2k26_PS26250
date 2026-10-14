import { mkdirSync, writeFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
import { buildScenario } from '../src/scenario.js';

const base = new URL(process.env.INGESTION_DEMO_URL ?? 'http://127.0.0.1:3100');
if (!['http:', 'https:'].includes(base.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password) throw new Error('Scenario credentials may only be sent to a loopback API.');
if (process.argv.slice(2).some((arg) => arg !== '--fast')) throw new Error('Usage: npm run scenario -- [--fast]');
const sources = JSON.parse(process.env.INGESTION_SOURCES_JSON ?? '[]');
const scenario = buildScenario({ sources, intervalMs: process.argv.includes('--fast') ? 100 : 5000 });
mkdirSync('var', { recursive: true }); writeFileSync('var/scenario-last.json', JSON.stringify(scenario, null, 2));
for (const step of scenario.steps) {
  if (step.delayMs) await delay(step.delayMs);
  console.log(JSON.stringify({ fixture: true, runId: scenario.runId, phase: step.label }));
  for (const event of step.events) {
    // Base short validity on actual send time so network latency cannot make
    // the fast demo expire the assertion before it reaches ingestion.
    if (event.type === 'crew.availability' && event.sequence === 2) {
      event.observedAt = new Date().toISOString();
      event.validUntil = new Date(Date.now() + (process.argv.includes('--fast') ? 100 : 5000)).toISOString();
    }
    const source = sources.find((s) => s.sourceId === event.sourceId);
    const response = await fetch(new URL('/v1/events', base), { method: 'POST',
      headers: { Authorization: `Bearer ${source.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(event), signal: AbortSignal.timeout(10000) });
    const result = await response.json();
    if (!response.ok) throw new Error(`Scenario ingestion failed: ${result.error?.code ?? response.status}.`);
    console.log(JSON.stringify({ type: event.type, disposition: result.disposition, duplicate: result.duplicate, delivery: result.delivery }));
  }
}
writeFileSync('var/scenario-last.json', JSON.stringify(scenario, null, 2));
console.log('Fictional scenario complete. Inspect fixture-prefixed entities in the read-only monitor. No operational decisions were generated.');
