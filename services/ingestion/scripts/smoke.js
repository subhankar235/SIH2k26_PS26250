import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { startServer } from '../src/server.js';

const run = promisify(execFile);
const port = process.env.INGESTION_SMOKE_PORT ?? '31870';
const runtime = await startServer({ ...process.env, PORT: port, INGESTION_DB_PATH: 'var/smoke.sqlite' });
try {
  const health = await fetch(`http://127.0.0.1:${port}/health/ready`);
  if (health.status !== 200) throw new Error('Smoke server is not ready.');
  for (const argument of [[], ['--replay']]) {
    const result = await run(process.execPath, ['--env-file-if-exists=.env', 'scripts/demo.js', ...argument], {
      env: { ...process.env, INGESTION_DEMO_URL: `http://127.0.0.1:${port}` }, timeout: 30000,
    });
    process.stdout.write(result.stdout);
  }
} finally { await runtime.close(); }
