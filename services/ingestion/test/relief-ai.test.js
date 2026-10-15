import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadReliefAIConfig, createReliefAnnotator } from '../src/agents/annotations.js';

const agents = ['fleet', 'crew', 'weather', 'airport', 'cargo'];
function input() {
  return { runId: 'c3af3cc6-fbee-46da-90d2-95cb9aad6dc9', revision: 2,
    agentReports: agents.map(agentId => ({ agentId, findings: [{ id: `${agentId}:1`, code: 'available',
      message: 'Fictional fixture finding.', entityIds: ['SIM-FIXTURE'] }], eligibleIds: ['SIM-FIXTURE'] })) };
}
function response(ids, overrides = {}) {
  return new Response(JSON.stringify({ model: 'gemma3:270m', done: true, response: JSON.stringify({ findingIds: ids }), ...overrides }));
}
function config(overrides = {}) { return loadReliefAIConfig({ RELIEF_AI_MODE: 'ollama', ...overrides }); }

test('AI configuration defaults to deterministic and allows only canonical loopback origins', () => {
  assert.equal(loadReliefAIConfig({}).mode, 'deterministic');
  assert.equal(config().ollamaUrl, 'http://127.0.0.1:11434');
  for (const origin of ['http://localhost:11434', 'http://[::1]:11434']) assert.equal(config({ OLLAMA_URL: origin }).ollamaUrl, origin);
  for (const origin of ['http://evil.test:11434', 'https://localhost:11434', 'http://127.0.0.1:11434/path',
    'http://user:secret@localhost:11434', 'http://127.1:11434', 'http://localhost:11434/?q=1', 'http://localhost:11434/#x']) {
    assert.throws(() => config({ OLLAMA_URL: origin }), /configuration/);
  }
  for (const env of [{ RELIEF_AI_MODE: 'cloud' }, { RELIEF_AI_TIMEOUT_MS: '0' }, { RELIEF_AI_NUM_CTX: '999999' },
    { RELIEF_AI_MODELS_JSON: '{}' }, { RELIEF_AI_MODELS_JSON: '{broken' },
    { RELIEF_AI_MODELS_JSON: JSON.stringify({ ...config().models, outsider: 'gemma3:270m' }) },
    { RELIEF_AI_MODELS_JSON: JSON.stringify({ ...config().models, fleet: 'https://remote.test' }) }]) {
    assert.throws(() => config(env), /configuration/);
  }
});

test('deterministic annotations carry revision identity and never call a model', async () => {
  const annotator = createReliefAnnotator(loadReliefAIConfig({}), { fetchImpl: () => { throw new Error('must not fetch'); } });
  const result = await annotator.annotate(input());
  assert.equal(result.runId, input().runId); assert.equal(result.revision, 2);
  assert.equal(result.mode, 'deterministic'); assert.deepEqual(result.modelsUsed, []);
  assert.ok(result.highlights.every(h => h.status === 'deterministic' && h.findingIds.length === 1));
  await annotator.close();
});

test('local models select only allowed IDs under strict schema with no tools', async () => {
  const requests = [];
  const annotator = createReliefAnnotator(config(), { fetchImpl: async (url, options) => {
    requests.push({ url, options });
    const body = JSON.parse(options.body);
    return response([JSON.parse(body.prompt).findings[0].id], { model: body.model });
  } });
  const result = await annotator.annotate(input());
  assert.equal(result.mode, 'ollama'); assert.equal(requests.length, 5);
  assert.equal(result.modelsUsed.length, 2);
  assert.ok(result.highlights.every(h => h.status === 'model' && h.findingIds[0] === `${h.agentId}:1`));
  const body = JSON.parse(requests[0].options.body);
  assert.equal(body.stream, false); assert.equal(body.format.additionalProperties, false);
  assert.equal(body.think, false); assert.equal(body.keep_alive, 0);
  assert.equal(body.tools, undefined); assert.equal(requests[0].options.redirect, 'error');
  assert.equal(requests[0].url, 'http://127.0.0.1:11434/api/generate');
  await annotator.close();
});

test('malformed output, invented IDs, prose, duplicate IDs and missing model fail to labelled fallback', async () => {
  for (const reply of [new Response('{broken'), response(['invented']), response(['fleet:1', 'fleet:1']),
    response(['fleet:1'], { response: JSON.stringify({ findingIds: ['fleet:1'], message: 'invented prose' }) }),
    response(['fleet:1'], { done: false }), response(['fleet:1'], { model: 'not-configured' }),
    new Response('sensitive server error', { status: 404 })]) {
    const annotator = createReliefAnnotator(config(), { fetchImpl: async () => reply.clone() });
    const result = await annotator.annotate(input());
    assert.equal(result.mode, 'deterministic-fallback');
    assert.ok(result.highlights.every(h => h.status === 'deterministic-fallback'));
    assert.deepEqual(result.modelsUsed, []);
    assert.ok(!JSON.stringify(result).includes('sensitive'));
    await annotator.close();
  }
});

test('timeout and response byte limits fail closed', async () => {
  for (const fetchImpl of [async () => new Promise(() => {}), async () => new Response('X'.repeat(2049))]) {
    const annotator = createReliefAnnotator(config({ RELIEF_AI_TIMEOUT_MS: '20', RELIEF_AI_MAX_RESPONSE_BYTES: '1024' }), { fetchImpl });
    const result = await annotator.annotate(input());
    assert.equal(result.mode, 'deterministic-fallback');
    await annotator.close();
  }
});

test('single flight saturates to fallback and shutdown aborts the pending model request', async () => {
  let signal;
  const annotator = createReliefAnnotator(config(), { fetchImpl: async (_url, options) => {
    signal = options.signal; return new Promise(() => {});
  } });
  const pending = annotator.annotate(input());
  const busy = await annotator.annotate(input());
  assert.equal(busy.mode, 'deterministic-fallback');
  assert.ok(busy.highlights.every(h => h.reasonCode === 'capacity'));
  await annotator.close();
  assert.equal(signal.aborted, true);
  assert.equal((await pending).mode, 'deterministic-fallback');
  assert.ok((await annotator.annotate(input())).highlights.every(h => h.reasonCode === 'closed'));
});

test('the five specialist report contract rejects missing, duplicate and excessive data', async () => {
  const annotator = createReliefAnnotator(loadReliefAIConfig({}));
  const original = input();
  for (const bad of [{ ...original, revision: 21 }, { ...original, runId: 'arbitrary' },
    { ...original, runId: [original.runId] },
    { ...original, agentReports: original.agentReports.slice(1) },
    { ...original, agentReports: [original.agentReports[0], ...original.agentReports.slice(0, 4)] },
    { ...original, agentReports: original.agentReports.map(r => ({ ...r, findings: Array(101).fill(r.findings[0]) })) }]) {
    await assert.rejects(annotator.annotate(bad), /annotation input/);
  }
  await annotator.close();
});

test('programmatic configuration cannot bypass loopback validation', () => {
  assert.throws(() => createReliefAnnotator({ ...config(), ollamaUrl: 'http://remote.test:11434' }), /configuration/);
});

test('empty specialist findings need no model call and remain explicit', async () => {
  const empty = input();
  empty.agentReports = empty.agentReports.map(r => ({ ...r, findings: [] }));
  const annotator = createReliefAnnotator(config(), { fetchImpl: () => { throw new Error('must not fetch'); } });
  const result = await annotator.annotate(empty);
  assert.equal(result.mode, 'deterministic');
  assert.ok(result.highlights.every(h => h.status === 'deterministic' && h.findingIds.length === 0));
  await annotator.close();
});

test('body streaming limits and stalled body reads trigger explicit fallback', async () => {
  for (const fetchImpl of [async () => new Response(new ReadableStream({ start(stream) {
    stream.enqueue(new Uint8Array(1025)); stream.close();
  } })), async () => new Response(new ReadableStream({ start() {} }))]) {
    const annotator = createReliefAnnotator(config({ RELIEF_AI_TIMEOUT_MS: '20', RELIEF_AI_MAX_RESPONSE_BYTES: '1024' }), { fetchImpl });
    const result = await annotator.annotate(input());
    assert.equal(result.mode, 'deterministic-fallback');
    assert.ok(result.highlights.every(h => ['timeout', 'response-too-large'].includes(h.reasonCode)));
    await annotator.close();
  }
});
