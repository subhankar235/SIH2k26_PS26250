const FEATURE_DEFINITION = ['intercept', 'day/30', 'sin(2*pi*day/7)', 'cos(2*pi*day/7)'];
const FORECAST_BOUNDS = { min: 0, max: 10000, maxDay: 3650 };

function features(day) { return [1, day / 30, Math.sin(2 * Math.PI * day / 7), Math.cos(2 * Math.PI * day / 7)]; }

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

// Solve the four-feature normal equations using pivoted Gaussian elimination.
function fitOLS(rows) {
  const matrix = Array.from({ length: 4 }, () => Array(5).fill(0));
  for (const { day, demand } of rows) {
    const x = features(day);
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) matrix[i][j] += x[i] * x[j];
      matrix[i][4] += x[i] * demand;
    }
  }
  for (let column = 0; column < 4; column++) {
    let pivot = column;
    for (let row = column + 1; row < 4; row++) {
      if (Math.abs(matrix[row][column]) > Math.abs(matrix[pivot][column])) pivot = row;
    }
    [matrix[column], matrix[pivot]] = [matrix[pivot], matrix[column]];
    const divisor = matrix[column][column];
    if (Math.abs(divisor) < 1e-10) throw new Error('Synthetic demand training matrix is singular.');
    for (let j = column; j < 5; j++) matrix[column][j] /= divisor;
    for (let row = 0; row < 4; row++) {
      if (row === column) continue;
      const factor = matrix[row][column];
      for (let j = column; j < 5; j++) matrix[row][j] -= factor * matrix[column][j];
    }
  }
  return matrix.map(row => row[4]);
}

function predict(coefficients, day) {
  return features(day).reduce((sum, feature, index) => sum + feature * coefficients[index], 0);
}

export function trainDemandModel({ seed = 26250, samples = 120 } = {}) {
  if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295 || !Number.isInteger(samples) || samples < 20 || samples > 1000) {
    throw new Error('Invalid synthetic demand training options.');
  }
  const random = seededRandom(seed);
  const rows = Array.from({ length: samples }, (_, day) => ({ day,
    demand: Math.round(250 + 2 * day + 50 * Math.sin(2 * Math.PI * day / 7) + 15 * Math.cos(2 * Math.PI * day / 7) + 30 * (random() - 0.5)) }));
  // Shuffle independently of the feature values before reserving the test split.
  for (let i = rows.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [rows[i], rows[j]] = [rows[j], rows[i]];
  }
  const testCount = Math.max(4, Math.floor(samples * 0.2));
  const heldOut = rows.slice(0, testCount);
  const training = rows.slice(testCount);
  const coefficients = fitOLS(training);
  const baseline = training.reduce((sum, row) => sum + row.demand, 0) / training.length;
  const mae = heldOut.reduce((sum, row) => sum + Math.abs(predict(coefficients, row.day) - row.demand), 0) / heldOut.length;
  const baselineMae = heldOut.reduce((sum, row) => sum + Math.abs(baseline - row.demand), 0) / heldOut.length;
  return { version: 1, kind: 'synthetic-demand-ols', simulation: true, seed, samples,
    featureDefinition: [...FEATURE_DEFINITION], coefficients, trainingCount: training.length, testCount,
    split: { trainingDays: training.map(row => row.day).sort((a, b) => a - b), testDays: heldOut.map(row => row.day).sort((a, b) => a - b) },
    evaluation: { mae, baselineMae }, forecastBounds: { ...FORECAST_BOUNDS } };
}

export function forecastDemand(model, day) {
  if (!Number.isFinite(day) || model?.version !== 1 || model.kind !== 'synthetic-demand-ols' || model.simulation !== true ||
    !Array.isArray(model.coefficients) || model.coefficients.length !== 4 || !model.coefficients.every(Number.isFinite)) {
    throw new Error('Invalid synthetic demand forecast input.');
  }
  const boundedDay = Math.min(FORECAST_BOUNDS.maxDay, Math.max(0, day));
  const prediction = predict(model.coefficients, boundedDay);
  if (!Number.isFinite(prediction)) throw new Error('Invalid synthetic demand forecast input.');
  return Math.round(Math.min(FORECAST_BOUNDS.max, Math.max(FORECAST_BOUNDS.min, prediction)));
}
