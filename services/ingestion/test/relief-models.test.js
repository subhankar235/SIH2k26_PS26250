import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trainDemandModel, forecastDemand } from '../src/forecasting/demand.js';

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

test('OLS coefficients fit training records only and evaluation excludes their targets', () => {
  const model = trainDemandModel();
  // Reconstruct the published dataset, not the implementation's fitting algorithm.
  let state = model.seed;
  const records = Array.from({ length: model.samples }, (_, day) => {
    state = (1664525 * state + 1013904223) % (2 ** 32);
    const angle = 2 * Math.PI * day / 7;
    return { day, x: [1, day / 30, Math.sin(angle), Math.cos(angle)],
      demand: Math.round(250 + 2 * day + 50 * Math.sin(angle) + 15 * Math.cos(angle) + 30 * (state / (2 ** 32) - 0.5)) };
  });
  const training = model.split.trainingDays.map(day => records[day]);
  const heldOut = model.split.testDays.map(day => records[day]);
  const prediction = record => record.x.reduce((sum, feature, index) => sum + feature * model.coefficients[index], 0);
  // Necessary OLS condition: the training residual is orthogonal to every column.
  // Fitting all rows instead leaks test targets and violates these four conditions.
  for (let feature = 0; feature < 4; feature++) {
    const gradient = training.reduce((sum, record) => sum + (record.demand - prediction(record)) * record.x[feature], 0);
    assert.ok(Math.abs(gradient) < 1e-6, `Training residual gradient ${feature} is ${gradient}`);
  }
  const mean = training.reduce((sum, record) => sum + record.demand, 0) / training.length;
  const mae = heldOut.reduce((sum, record) => sum + Math.abs(record.demand - prediction(record)), 0) / heldOut.length;
  const baselineMae = heldOut.reduce((sum, record) => sum + Math.abs(record.demand - mean), 0) / heldOut.length;
  assert.ok(Math.abs(model.evaluation.mae - mae) < 1e-10);
  assert.ok(Math.abs(model.evaluation.baselineMae - baselineMae) < 1e-10);
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
