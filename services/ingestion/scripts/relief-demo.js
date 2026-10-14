import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
const base = new URL(process.env.INGESTION_DEMO_URL ?? 'http://127.0.0.1:3100');
if (!['http:', 'https:'].includes(base.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password) throw new Error('Fixture admin credentials may only be sent to loopback.');
if (process.argv.slice(2).some((arg) => arg !== '--fast')) throw new Error('Usage: npm run relief:demo -- [--fast]');
const request = async (path, body) => {
  const response = await fetch(new URL(path, base), { method: body ? 'POST' : 'GET', redirect: 'error',
    headers: { Authorization: `Bearer ${process.env.INGESTION_ADMIN_TOKEN}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(10000) });
  const result = await response.json(); if (!response.ok) throw new Error(`Relief simulation request failed: ${result.error?.code ?? response.status}`); return result;
};
const current = await request('/v1/simulation');
const command = { scenario: 'civilian-relief', commandId: randomUUID(), ...(current.status === 'ready' ? { replaceRunId: current.world.runId } : {}) };
let result = await request('/v1/simulation/start', command);
const replay = await request('/v1/simulation/start', command);
if (!replay.command.replayed || replay.world.runId !== result.world.runId) throw new Error('Command replay verification failed.');
const print = () => console.log(JSON.stringify({ fictional: true, revision: result.world.revision, phase: result.history.at(-1).phase,
  objective: result.plan.objective, proposals: result.plan.assignments.length, unmet: result.plan.unserved.length,
  verified: result.validation.valid, status: result.plan.status, annotationStatus: result.annotations.status }));
print();
while (result.nextPhase) {
  await delay(process.argv.includes('--fast') ? 100 : 6000);
  result = await request('/v1/simulation/step', { commandId: randomUUID(), runId: result.world.runId, expectedRevision: result.world.revision, phase: result.nextPhase }); print();
}
console.log('Civilian simulation complete. The read-only monitor shows fictional proposals, specialist reports and forecast evaluation. No deliveries were executed.');
