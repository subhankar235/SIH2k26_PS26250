import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { EVENT_TYPES, validateEvent } from '../src/contracts.js';
import { sampleEvent } from '../src/sample-events.js';

test('fictional sample generators satisfy all runtime contracts', () => {
  const now = Date.parse('2026-10-15T06:00:00Z');
  for (const type of EVENT_TYPES) assert.equal(validateEvent(sampleEvent(type, { now }), { now }).type, type);
});
test('credential generator creates separate secrets without printing them and refuses overwrite', (t) => {
  const directory = mkdtempSync(join(tmpdir(), 'logistics-credentials-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, '.env');
  const result = spawnSync(process.execPath, ['scripts/credentials.js', '--write', path], { encoding: 'utf8' });
  assert.equal(result.status, 0);
  const contents = readFileSync(path, 'utf8');
  const sourceLine = contents.split('\n').find((line) => line.startsWith('INGESTION_SOURCES_JSON='));
  const sources = JSON.parse(sourceLine.slice('INGESTION_SOURCES_JSON='.length));
  const admin = contents.split('\n').find((line) => line.startsWith('INGESTION_ADMIN_TOKEN=')).split('=')[1];
  const viewer = contents.split('\n').find((line) => line.startsWith('MONITOR_VIEWER_TOKEN=')).split('=')[1];
  assert.match(viewer, /^[A-Za-z0-9_-]{48}$/);
  assert.equal(sources.length, 5); assert.equal(new Set([admin, viewer, ...sources.map((s) => s.token)]).size, 7);
  assert.ok(![admin, viewer, ...sources.map((s) => s.token)].some((token) => result.stdout.includes(token)));
  const again = spawnSync(process.execPath, ['scripts/credentials.js', '--write', path], { encoding: 'utf8' });
  assert.notEqual(again.status, 0); assert.equal(readFileSync(path, 'utf8') === contents, true);
});
test('committed generated contract files match their generator', () => {
  const result = spawnSync(process.execPath, ['scripts/generate-contracts.js', '--check'], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
});
