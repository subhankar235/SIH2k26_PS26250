import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trainDemandModel, forecastDemand } from '../src/relief-models.js';

test('synthetic OLS training is reproducible with an independent held-out evaluation', () => {
  const model = trainDemandModel();
  assert.deepEqual(model, trainDemandModel());
  assert.notDeepEqual(model.coefficients, trainDemandModel({ seed: 99 }).coefficients);
  assert.equal(model.seed, 26250);
  assert.equal(model.trainingCount + model.testCount, 120);
  assert.equal(model.testCount, 24);
  assert.equal(new Set([...model.split.trainingDays, ...model.split.testDays]).size, 120);
  assert.ok(model.evaluation.mae < model.evaluation.baselineMae / 2);
  assert.ok(model.evaluation.mae > 0);
  assert.deepEqual(JSON.parse(JSON.stringify(model)), model);
});

test('forecasts remain finite and bounded, including extreme finite extrapolation', () => {
  const model = trainDemandModel();
  for (const day of [0, 30, 121, -1e200, 1e200]) {
    const demand = forecastDemand(model, day);
    assert.ok(Number.isInteger(demand));
    assert.ok(demand >= 0 && demand <= 10000);
  }
  for (const day of [NaN, Infinity, -Infinity, '4']) assert.throws(() => forecastDemand(model, day));
  assert.throws(() => forecastDemand({ ...model, coefficients: [Infinity, 0, 0, 0] }, 5));
});

test('training rejects invalid or excessive dataset requests', () => {
  for (const options of [{ seed: -1 }, { seed: NaN }, { samples: 3 }, { samples: 1001 }, { samples: 20.5 }]) {
    assert.throws(() => trainDemandModel(options));
  }
});
