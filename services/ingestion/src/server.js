import { loadConfig } from './config.js';
import { EventStore } from './store.js';
import { createKafkaAdapter, OutboxPublisher } from './publisher.js';
import { createApp } from './app.js';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { installShutdownHandlers } from './shutdown.js';

function logger(message, fields = {}) {
  process.stdout.write(`${JSON.stringify({ timestamp: new Date().toISOString(), message, ...fields })}\n`);
}

export async function startServer(env = process.env) {
  const config = loadConfig(env);
  const store = new EventStore({ path: config.dbPath, maxPending: config.maxPending });
  let ready = true;
  const publisher = new OutboxPublisher({ store, adapter: config.kafka.brokers.length ? createKafkaAdapter(config.kafka) : null,
    logger, maxAttempts: config.maxAttempts, baseDelayMs: config.baseDelayMs, maxDelayMs: config.maxDelayMs });
  const app = createApp({ config, store, publisher, logger, isReady: () => ready });
  const server = app.listen(config.port, config.host);
  server.requestTimeout = 15000; server.headersTimeout = 10000;
  server.keepAliveTimeout = 5000; server.maxHeadersCount = 64; server.maxConnections = 200;
  try {
    await new Promise((resolve, reject) => { server.once('listening', resolve); server.once('error', reject); });
  } catch (error) { await publisher.stop(); store.close(); throw error; }
  publisher.start(config.flushIntervalMs);
  logger('service.started', { host: config.host, port: config.port, kafkaEnabled: publisher.enabled });
  let closing;
  function close() {
    if (closing) return closing;
    ready = false;
    closing = (async () => {
      const force = setTimeout(() => server.closeAllConnections(), 10000); force.unref();
      try {
        const results = await Promise.allSettled([new Promise((resolve) => server.close(resolve)), publisher.stop()]);
        clearTimeout(force); store.close(); logger('service.stopped');
        const failure = results.find((result) => result.status === 'rejected');
        if (failure) throw failure.reason;
      } catch (error) { clearTimeout(force); throw error; }
    })();
    return closing;
  }
  return { server, store, publisher, close };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  startServer().then((runtime) => {
    installShutdownHandlers(runtime, { logger });
  }).catch((error) => {
    const reason = error.message?.startsWith('Invalid configuration:') ? error.message : 'Startup failed.';
    process.stderr.write(`${reason}\n`); process.exitCode = 1;
  });
}
