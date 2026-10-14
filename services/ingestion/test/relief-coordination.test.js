import assert from 'node:assert/strict';
import test from 'node:test';
import { buildReliefCoordination } from '../src/relief-coordination.js';
import { createReliefWorld, advanceReliefWorld } from '../src/relief-world.js';
import { optimizeReliefWorld, validateReliefPlan } from '../src/relief-planner.js';

function evidence() {
  const world = createReliefWorld({ runId: '00000000-0000-4000-8000-000000000001', now: 0 });
  const plan = optimizeReliefWorld(world);
  return { world, plan, validation: validateReliefPlan(world, plan) };
}

test('coordination deterministically links specialist findings to the verified supervisor decision', () => {
  const { world, plan, validation } = evidence();
  const before = structuredClone({ world, plan, validation });
  const result = buildReliefCoordination(world, plan, validation);
  assert.equal(result.version, 1); assert.equal(result.topology, 'specialists-supervisor');
  assert.deepEqual(result.decision, { status: 'verified', servedPriority: 9, assignedCount: 2 });
  assert.deepEqual(buildReliefCoordination(world, plan, validation), result);
  assert.deepEqual({ world, plan, validation }, before);
  assert.equal(new Set(result.messages.map(m => m.id)).size, result.messages.length);
  const findings = new Map(plan.agentReports.flatMap(r => r.findings.map(f => [f.id, f])));
  const entities = new Set(['aircraft', 'crews', 'airports', 'requests'].flatMap(k => world[k].map(e => e.id)));
  for (const message of result.messages) {
    assert.deepEqual(Object.keys(message).sort(), ['entityIds', 'findingIds', 'from', 'id', 'kind', 'summary', 'to']);
    assert.ok(message.summary.length > 0 && message.summary.length <= 500);
    assert.ok(message.findingIds.every(id => findings.has(id)));
    assert.ok(message.entityIds.every(id => entities.has(id)));
  }
  for (const report of plan.agentReports) {
    const message = result.messages.find(m => m.from === report.agentId && m.to === 'supervisor');
    assert.ok(message); assert.deepEqual(message.findingIds, report.findings.map(f => f.id).sort());
  }
  assert.ok(result.messages.some(m => m.from === 'supervisor' && m.kind === 'resolution'));
});

test('blocked and empty decisions retain actual adverse evidence', () => {
  const initial = evidence(); const world = advanceReliefWorld(initial.world, 'weather-change');
  const plan = optimizeReliefWorld(world);
  const result = buildReliefCoordination(world, plan, validateReliefPlan(world, plan));
  const blocked = plan.agentReports.find(r => r.agentId === 'weather').findings.filter(f => f.code !== 'ELIGIBLE');
  assert.ok(blocked.length);
  assert.ok(blocked.every(f => result.messages.some(m => m.findingIds.includes(f.id))));
  world.tick = 6; const empty = optimizeReliefWorld(world);
  assert.deepEqual(buildReliefCoordination(world, empty, validateReliefPlan(world, empty)).decision,
    { status: 'verified', servedPriority: 0, assignedCount: 0 });
});

test('coordination refuses to claim verification for rejected or tampered plans', () => {
  const { world, plan } = evidence();
  assert.throws(() => buildReliefCoordination(world, plan, { valid: false, errors: ['failed'] }), /verified/i);
  assert.throws(() => buildReliefCoordination(world, plan, { valid: true, errors: ['failed'] }), /verified/i);
  const tampered = structuredClone(plan); tampered.agentReports[0].findings[0].entityIds = ['SIM-INVENTED'];
  assert.throws(() => buildReliefCoordination(world, tampered, { valid: true, errors: [] }), /evidence/i);
  const unknown = structuredClone(plan); unknown.assignments[0].aircraftId = 'SIM-INVENTED';
  assert.throws(() => buildReliefCoordination(world, unknown, { valid: true, errors: [] }), /evidence/i);
  const objective = structuredClone(plan); objective.objective.servedPriority = 99;
  assert.throws(() => buildReliefCoordination(world, objective, { valid: true, errors: [] }), /verified/i);
});
