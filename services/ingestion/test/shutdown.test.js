import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { installShutdownHandlers } from '../src/shutdown.js';

test('a broker cleanup that never settles triggers the overall shutdown failure deadline', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const signals = new EventEmitter(); const exits = []; const logs = [];
  const dispose = installShutdownHandlers({ close: () => new Promise(() => {}) }, {
    signals, timeoutMs: 15000, exit: (code) => exits.push(code), logger: (message) => logs.push(message),
  });
  t.after(dispose); signals.emit('SIGTERM');
  t.mock.timers.tick(14999); assert.deepEqual(exits, []);
  t.mock.timers.tick(1); assert.deepEqual(exits, [1]); assert.ok(logs.includes('service.shutdown_timeout'));
});
test('successful shutdown cancels the deadline and repeated signals do not close twice', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const signals = new EventEmitter(); let closes = 0; const exits = [];
  const dispose = installShutdownHandlers({ close: async () => { closes++; } }, {
    signals, timeoutMs: 15000, exit: (code) => exits.push(code), logger: () => {},
  });
  t.after(dispose); signals.emit('SIGINT'); signals.emit('SIGTERM'); await new Promise(setImmediate);
  t.mock.timers.tick(15000); assert.equal(closes, 1); assert.deepEqual(exits, []);
});
test('a rejected shutdown exits as a failure without leaking the underlying error', async (t) => {
  const signals = new EventEmitter(); const exits = []; const logs = [];
  const dispose = installShutdownHandlers({ close: async () => { throw new Error('secret connection data'); } }, {
    signals, exit: (code) => exits.push(code), logger: (message) => logs.push(message),
  });
  t.after(dispose); signals.emit('SIGTERM'); await new Promise(setImmediate);
  assert.deepEqual(exits, [1]); assert.deepEqual(logs, ['service.shutdown_failed']);
});
