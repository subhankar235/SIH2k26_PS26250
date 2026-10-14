import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

// KafkaJS2.2.4 schedules an idle queue at (-1 - Date.now()), creating a repeated
// 1ms timer and Node24 TimeoutNegativeWarning. Only queue nonempty work.
// This explicit, reviewed setup step is used instead of third-party install hooks.
const require = createRequire(import.meta.url);
const root = dirname(require.resolve('kafkajs/package.json'));
const path = join(root, 'src/network/requestQueue/index.js');
const expected = 'b55986089c14f8f7bfc377922e2e65b3e4c1e7c7af2752d3b10a75dfe9e9260c';
const anchor = '  scheduleCheckPendingRequests() {\n';
const guard = '    // Local Node24 compatibility: idle queues need no throttle timer.\n    if (this.pending.length === 0) return\n';
const current = readFileSync(path, 'utf8');
const original = current.replace(anchor + guard, anchor);
if (createHash('sha256').update(original).digest('hex') !== expected) {
  throw new Error('KafkaJS source differs from the reviewed 2.2.4 file; refusing to patch.');
}
const patched = original.replace(anchor, anchor + guard);
if (current !== patched) writeFileSync(path, patched);
process.stdout.write('KafkaJS Node24 compatibility patch verified.\n');
