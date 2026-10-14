/** The CLI owns a hard shutdown deadline, even if a broker library never settles. */
export function installShutdownHandlers(runtime, { signals = process, timeoutMs = 15000,
  exit = (code) => process.exit(code), logger = () => {} } = {}) {
  let shuttingDown = false; let deadline;
  const dispose = () => {
    clearTimeout(deadline); signals.removeListener('SIGINT', shutdown); signals.removeListener('SIGTERM', shutdown);
  };
  const shutdown = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    deadline = setTimeout(() => { logger('service.shutdown_timeout'); exit(1); }, timeoutMs);
    deadline.unref?.();
    Promise.resolve().then(() => runtime.close()).then(dispose, () => {
      dispose(); logger('service.shutdown_failed'); exit(1);
    });
  };
  signals.once('SIGINT', shutdown); signals.once('SIGTERM', shutdown);
  return dispose;
}
