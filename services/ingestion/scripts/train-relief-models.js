import { parseArgs } from 'node:util';
import { writeFileSync } from 'node:fs';
import { trainDemandModel, forecastDemand } from '../src/forecasting/demand.js';

try {
  const { values } = parseArgs({ options: { seed: { type: 'string', default: '26250' },
    samples: { type: 'string', default: '120' }, output: { type: 'string' } }, allowPositionals: false });
  if (!/^[0-9]+$/.test(values.seed) || !/^[0-9]+$/.test(values.samples)) throw new Error('Invalid training arguments.');
  const model = trainDemandModel({ seed: Number(values.seed), samples: Number(values.samples) });
  const artifact = { ...model, exampleForecasts: [120, 121, 122].map(day => ({ day, demand: forecastDemand(model, day) })) };
  const json = `${JSON.stringify(artifact, null, 2)}\n`;
  if (values.output) writeFileSync(values.output, json, { flag: 'wx' });
  else process.stdout.write(json);
} catch {
  console.error('Relief training failed. Use --seed UINT32 --samples 20..1000 [--output NEW_FILE].');
  process.exitCode = 1;
}
