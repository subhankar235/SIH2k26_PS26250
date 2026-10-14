import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createReliefWorld } from '../src/relief-world.js';
import { optimizeReliefWorld } from '../src/relief-planner.js';
import { loadReliefAIConfig, createReliefAnnotator } from '../src/relief-ai.js';
const config = loadReliefAIConfig({ ...process.env, RELIEF_AI_MODE: 'ollama', RELIEF_AI_TIMEOUT_MS: '60000' });
const annotator = createReliefAnnotator(config); const world = createReliefWorld();
try {
  const reports = optimizeReliefWorld(world).agentReports;
  const start = performance.now();
  const result = await annotator.annotate({ runId: world.runId, revision: world.revision, agentReports: reports });
  console.log(JSON.stringify({ mode: result.mode, modelsUsed: result.modelsUsed, elapsedMs: Math.round(performance.now() - start),
    statuses: result.highlights.map(({ agentId, status, model, reasonCode }) => ({ agentId, status, model, reasonCode })) }));
  assert.equal(result.mode, 'ollama'); assert.equal(result.modelsUsed.length, 2);
  assert.ok(result.highlights.every((h) => h.status === 'model'));
  for (const highlight of result.highlights) assert.ok(highlight.findingIds.every((id) => reports.find((r) => r.agentId === highlight.agentId).findings.some((f) => f.id === id)));
  const response = await fetch(`${config.ollamaUrl}/api/tags`, { redirect: 'error', signal: AbortSignal.timeout(5000) });
  assert.equal(response.ok, true); const tags = await response.json();
  const models = tags.models.filter((model) => result.modelsUsed.includes(model.name)).map(({ name, digest, size }) => ({ name, digest, size }));
  assert.equal(models.length, 2); mkdirSync('var', { recursive: true });
  writeFileSync('var/relief-model-smoke.json', JSON.stringify({ result, models }, null, 2));
  console.log('Two real local models passed evidence-ID validation; digests saved in ignored var/relief-model-smoke.json.');
} finally { await annotator.close(); }
