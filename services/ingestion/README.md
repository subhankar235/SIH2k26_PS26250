# Administrative logistics event gateway and monitor

A standalone JavaScript ingestion service for aircraft maintenance status, crew availability, weather observations, airport capacity, and ordinary relief cargo. It maintains an authenticated event history and source-specific latest observations, then delivers eligible changes to Kafka through a durable transactional outbox.

This module records observations. It does not create flight assignments, optimise military operations, process adversary intelligence, or allocate weapons. Sample data is fictional.

[Verification evidence for the monitoring increment](docs/validation-monitoring.md).

The complete fixed **civilian relief simulation** now adds five constraint specialists, bounded multi-objective optimization, independent verification, automatic replanning, a trained synthetic demand forecast, and two optional real local language models for validated evidence highlighting. [Detailed implementation guide](docs/CIVILIAN_ENGINE_GUIDE.md) covers architecture, models/datasets, algorithms, JavaScript/Kafka, persistence, setup and testing. This is a separate fictional engine; it does not optimize real gateway data or fulfil combat-planning requirements.

After starting the API and signing into the monitor, run `npm run relief:demo` in another terminal. The dashboard shows fictional proposals, unmet reasons, specialist reports, budget status, independent checks, forecast evaluation, model status and revision history. Use `npm run relief:train` for the synthetic model artifact; the guide explains installing/testing local Gemma/Qwen via `compose.ai.yaml` and enabling `RELIEF_AI_MODE=ollama`.

## Quick start

Requirements: Node **24.19.0 or later**, npm **11.17.0**. Run these commands from this directory:

```powershell
npm ci --ignore-scripts
npm run setup
npm run credentials
npm start
```

The credential generator creates an ignored `.env` file with separate random admin, viewer and per-domain source tokens. It refuses to overwrite an existing file and prints no tokens. The empty `.env.example` intentionally cannot start the server. Keep credentials private; file mode alone does not configure Windows ACLs.

Open `http://127.0.0.1:3100/monitor/` and enter the separate `MONITOR_VIEWER_TOKEN` from your private `.env`. For an existing credential file without that setting, run `npm run viewer:credentials` once, then restart the server. Never enter the admin or source token into the dashboard. The browser receives only a read-only 30-minute HttpOnly cookie; viewer sessions cannot write events or invoke admin endpoints.

In a second terminal, `npm run scenario` demonstrates five fictional domains, weather changes, maintenance reports, an airport closure report, sequence gaps, duplicate/stale events and validity expiry over about 35 seconds. `npm run scenario -- --fast` compresses timing for smoke checks. These are administrative source updates; no flight decisions are generated. The page polls every five seconds, so fast-mode phases can finish between polls. [Monitoring contracts, module map and demonstration](docs/monitoring.md) explain the full flow.

Default API: `http://127.0.0.1:3100`. In another terminal in this directory:

```powershell
npm run demo
npm run demo -- --replay
```

The demo ingests five domains, changes aircraft status, crew availability, weather and airport capacity, retries an identical event, archives a stale sequence, and archives an expired observation. It prints receipt/freshness summaries and operational counts. `--replay` reuses the saved fictional event bodies in `var/demo-last.json`; it demonstrates idempotency rather than sending a new scenario. A new default run uses new event IDs and increasing sequences. Sample JSON under `docs/` has fixed historical dates; use the demo for live timestamps.

With Kafka disabled, events are retained as **queued**. The demo's flush returns 503 `BROKER_DISABLED`; durable acceptance is still successful. No console adapter falsely marks delivery complete.

## Local Kafka

Docker engine must be running. This development broker is pinned to the tested Apache Kafka4.1.1 image digest, has one replica, and is exposed only on the loopback address:

```powershell
docker compose up -d --wait
```

Set `KAFKA_BROKERS=localhost:29092` in `.env`, then create the five topics and restart the API:

```powershell
npm run kafka:topics
npm start
```

In a third terminal, `npm run consumer` runs the independent durable read model. It uses `var/read-model.sqlite` and a stable consumer group, validates/quarantines broker messages, records checkpoints transactionally before acknowledgment, and handles crash replay. [Consumer runbook](docs/consumer.md) covers capacity, broker rewind and rebuild procedures. The dashboard reads the gateway database, so an outbox marked published does **not** imply the downstream reader processed it.

The topic setup is idempotent. It configures three partitions and one replica only when creating a new topic; it does not overwrite existing broker/topic settings. Default topic retention on creation follows `INGESTION_RETENTION_DAYS`. Existing broker retention must be managed separately.

```powershell
$env:KAFKA_TEST_BROKERS = 'localhost:29092'
npm run test:kafka
```

Additional verification commands (browser smoke needs a running local server, `.env` viewer/source credentials, Python and Playwright Chromium):

```powershell
npm run test:consumer:kafka
npm run smoke:pipeline
python -m pip install playwright
python -m playwright install chromium
npm run test:browser
```

The consumer integration fails when no test broker is configured. Browser smoke posts uniquely named fictional airport assertions, verifies actual updates/TTL through the UI, exports a secret-free snapshot and saves ignored screenshots in `var/`. Run it against an isolated development database when existing records matter.

This enabled integration test uses the actual broker and two different consumer groups. Without that environment variable it is explicitly skipped. `docker compose stop` stops this project's development broker while preserving its volume.

Remote brokers require `KAFKA_TLS=true`. Optional SASL requires both `KAFKA_SASL_USERNAME` and `KAFKA_SASL_PASSWORD`, TLS, and `KAFKA_SASL_MECHANISM` (`plain`, `scram-sha-256`, or `scram-sha-512`). Do not use the local single-replica broker as a production security or availability configuration.

## Contract and routes

See [OpenAPI](docs/openapi.json), [generated input schemas](docs/event-schemas.json), and [fictional examples](docs/sample-events.json). Schemas are generated from the runtime Zod branches. JSON Schema does not represent custom cross-field checks or the clock-dependent future-observation limit; runtime validation remains authoritative.

Every event supplies `schemaVersion:1`, UUID `eventId`, `sourceId`, `type`, `entityId`, positive safe-integer `sequence`, timezone-qualified `observedAt` and `validUntil`, and strict type-specific `data`. Timestamps normalize to UTC. Validity must be positive and at most seven days. Observations over sixty seconds in the future are rejected. Use pseudonymous crew IDs; names, contact information, arbitrary notes, and unknown fields are not accepted.

| Endpoint | Credential | Purpose |
|---|---|---|
| `GET /health/live`, `/health/ready` | None | Minimal liveness and local-store readiness |
| `POST /v1/events` | Source | Single-event durable acceptance; 201 new / 200 duplicate |
| `POST /v1/events/batch` | Source | Atomic `{events:[...]}` batch of 1..100; 200 ordered receipts |
| `GET /v1/events`, `/v1/events/:eventId` | Admin | Immutable history/replay and receipt lookup |
| `GET /v1/state` | Admin | Source-specific latest observations and freshness |
| `GET /v1/outbox` | Admin | Delivery metadata, without payload dumps |
| `POST /v1/outbox/:eventId/retry` | Admin | Audit and requeue dead work; JSON `{}` |
| `POST /v1/outbox/flush` | Admin | Bounded delivery drain; JSON `{}` |
| `POST /v1/retention` | Admin | Bounded history scan; `{}` or `{limit:100,after:0}` |
| `GET /v1/metrics`, `/v1/schema` | Admin | Counters/diagnostics and generated schemas |

History/state filters: `after` cursor, `limit`1..100, `sourceId`, `type`, `entityId`. Outbox filters: cursor/limit and `status` (`queued`, `dead`, `published`). Unknown/duplicate query parameters are rejected. Pagination is a live view, not a transactionally frozen snapshot. Historical replay has no write or publication side effects.

Writes authenticate the source first; a valid token cannot spoof another `sourceId` or an unconfigured event type. Admin and source tokens cannot be equal. Responses include `X-Request-ID`. Errors are `{error:{code,message,details?},requestId}`. Bodies are limited to256KiB, compressed requests are rejected, and pagination/batches/work are bounded. 429/503 responses have `Retry-After`. There is no permissive CORS, proxy trust, payload logging, or public diagnostic endpoint.

## Consistency and delivery

1. Validation and source authorisation precede persistence.
2. A SQLite transaction inserts immutable history, the source-specific latest-state reference, and queued outbox work together.
3. An exact event-ID/content retry returns its existing cursor. Conflicting reuse returns409; a batch rolls back completely on conflict or backlog exhaustion.
4. Lower/equal sequences and older observations are archived as stale; expired records are archived as expired. They do not overwrite latest state or enter the outbox. Sequences are compared only within `(sourceId,type,entityId)`; different feeds are not silently merged. Sequence gaps are quality warnings. Expired latest observations stay visibly expired.
5. The publisher sends only each topic/key stream's oldest queued record. Delayed retries block later queued records in that stream. A terminal dead record is visible to operators and releases later records; manual requeue can consequently send an older sequence after a newer one.
6. Publication is recorded only after Kafka acknowledgement with `acks=-1`. Persisted retry delays and attempt bounds lead to a visible dead record after exhaustion. Broker errors are stored as safe codes.

Delivery is **at least once**: a crash after broker acknowledgement and before the SQLite update may resend an event. Consumers must deduplicate by event ID, enforce source-specific sequence/observation ordering, and check `validUntil`. Kafka orders records within a partition; it does not give a globally ordered view across topics. Current-store readiness does not imply broker readiness; queued/dead counts and broker timestamps are available to admins.

Retention removes only old settled/history records that are not current projection targets. It preserves every queued/dead delivery. Once a historical event is purged, its event-ID deduplication record is also gone: idempotency is retained-history-bounded. Source sequence checks still protect the surviving projection, but an old purged ID with new higher-sequence content can be accepted again. Retention runs only when an admin invokes it; monitor disk use and set an appropriate policy. Kafka retention is a separate policy.

## Configuration and operations

Retention examines at most `limit` candidate events per call and returns `{deleted,scanned,nextCursor}`. Pass a non-null `nextCursor` as the next call's `after` value to continue the sweep. Protected or recent records still consume scan budget, so cleanup can advance past them without an unbounded search. Start a later sweep at `after:0` to reconsider previously protected records. The projection-reference lookup is indexed.

`.env.example` lists defaults. Source config is an array of `{sourceId,token,types}`. Source identifiers and event identifiers are bounded; type names come from the five fixed schema types. `INGESTION_MAX_PENDING` includes queued and dead delivery work, so dead records require operator attention. Rate limits are per-service-process fixed windows; source writes are charged per event, including batch members.

SQLite uses WAL, full synchronous writes, prepared statements, and a5s busy timeout. Run **one service process per database file on a local filesystem**. `node:sqlite` is a Node-maintained API whose stability varies by Node release; this project requires the tested24.19 runtime, which runs it without an experimental warning. Do not replace the runtime with an older release without checking compatibility.

SIGINT/SIGTERM stop acceptance, drain the current publication, and close resources. HTTP connections have a10s force-close deadline. CLI shutdown has a15s overall failure deadline even if broker cleanup never settles. Forced termination leaves durable queued work for restart and may cause redelivery. Remote deployment needs TLS termination, protected credentials/database/backups, monitoring, tested recovery procedures, and an explicit source-authority policy. There is no multi-replica store/limiter, aircraft-domain certification, or production throughput claim.

## KafkaJS compatibility step

KafkaJS2.2.4 schedules an idle request queue at `-1-Date.now()`, causing repeated1ms polling and Node24 `TimeoutNegativeWarning`. `npm run setup` verifies the complete original source checksum and inserts one guard that skips an empty queue. It is idempotent, leaves nonempty queue/throttle handling intact, and refuses unexpected dependency changes. No warning is suppressed. Review this patch when upgrading KafkaJS; install lifecycle scripts remain disabled, and this reviewed setup script is invoked explicitly.

## Tests and learning

```powershell
npm run check
npm run contracts:check
npm test
npm run test:coverage
npm audit
```

Unit/HTTP tests use real schema parsing, HTTP servers, and SQLite. Broker fault-injection tests use an explicit fake adapter; the separate enabled Kafka integration verifies actual delivery. [Middleware walkthrough](docs/javascript-learning.md) explains request parsing, authentication, validation, transactions, producers, and consumers. [Architecture decision](docs/decision.md) records the tradeoffs.

Regenerate committed contracts with `npm run contracts` after changing schemas/API documentation. Run `npm run contracts:check` to detect drift. The Dockerfile uses the same lifecycle-disabled install and explicit compatibility step, and runs as the unprivileged `node` user. Container credentials come from an environment file; persist `/app/var` in a volume. Containerised access to a remote broker requires the same TLS policy as any other remote broker.
