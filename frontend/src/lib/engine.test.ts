import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makePlan, verifyPlan, experiment } from './engine.ts';

test('feasible schedule passes independent checks', () => {
  const p = makePlan(4, 8);
  assert.equal(p.status, 'Feasible');
  assert.ok(verifyPlan(p, 4).every(c => c.pass));
});

test('impossible capacity is reported honestly', () => {
  assert.equal(makePlan(1, 4).status, 'Infeasible');
});

test('changed capacity invalidates prior result', () => {
  assert.ok(verifyPlan(makePlan(4, 8), 1).some(c => !c.pass));
});

test('seeded fault detection is reproducible', () => {
  const a = experiment(42, 30, 'Conflicting claims');
  const b = experiment(42, 30, 'Conflicting claims');
  assert.equal(a.injected, b.injected);
  assert.equal(a.detected, b.detected);
  assert.ok(a.detected > 0);
  assert.equal(a.baseline, 0);
});
