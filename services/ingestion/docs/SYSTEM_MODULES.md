# System modules and entry points

The complete current application lives in this service directory. Its `ingestion` name is historical and retained to preserve existing configuration, database paths, dependency installations and guide links. Modules run together in one process to preserve the synchronous event/replanning transaction. Kafka's reader is a separate process.

## Code map

| Module | Path | Responsibility |
| --- | --- | --- |
| Composition | `src/server.js`, `src/app.js` | Runtime lifecycle, HTTP/authentication and module wiring |
| Contracts | `src/contracts/events.js` | Canonical event validation, topics and schema exports |
| Platform | `src/platform/` | Configuration, shared errors and shutdown |
| Ingestion | `src/ingestion/` | Authorized acceptance, SQLite event history/projections/outbox, ordinary event fixtures |
| Transport | `src/transport/` | Kafka publisher, independent durable reader, consumer storage/CLI |
| Planning | `src/planning/` | World/configuration, bound inputs/TTL, exact optimizer/checker and atomic simulation orchestration |
| Agents | `src/agents/` | Autonomous deterministic negotiation, coordination evidence and optional model annotations |
| Forecasting | `src/forecasting/demand.js` | Synthetic OLS training, held-out evaluation and demand estimates |
| Integrations | `src/integrations/weather.js` | Validated explicit Open-Meteo refresh |
| Dashboard server | `src/dashboard/monitoring.js` | Read-only sessions and projection endpoints |
| Dashboard browser | `dashboard/` | Accessible browser rendering, evidence/plan/negotiation inspection |
| Verification | `test/`, `integration/`, `scripts/` | Offline tests, real-broker tests, browser fixtures and reproducible demos |

The planner calls agents and forecasting directly; accepted source events enter the planner through explicit scenario bindings. Kafka delivery follows commit. The independent Kafka reader does not feed the optimizer. Forecasting is displayed evidence; optional LLM annotations only select known findings. No new broker-mediated coordination or distributed-service claims are introduced by this directory split.

## Commands from the repository root

Install the service once, keeping its existing lockfile/install boundary:

```powershell
npm --prefix services/ingestion ci --ignore-scripts
npm run setup
```

No root `npm install` is required: the root package has no dependencies and delegates commands to the service. Generate credentials only for a new installation with `npm run credentials`; an existing `.env` must be preserved.

| Root command | Result |
| --- | --- |
| `npm start` | Start API, planner lifecycle and dashboard on the configured address |
| `npm run consumer` | Start the independent Kafka reader |
| `npm run verify` | Syntax, generated-contract freshness and full offline suite |
| `npm test` | Full offline suite |
| `npm run demo:offline` | Isolated HTTP/SQLite journey with temporary credentials/data; no running service/broker needed |
| `npm run demo` | Send the dynamic fictional scenario to the running configured API |
| `npm run test:pipeline` | Isolated real Kafka/source/replanning/TTL/reader/restart integration; configured `.env` and local broker required |
| `npm run test:pipeline -- --browser` | Same pipeline plus browser verification; Python Playwright/Chromium required |
| `npm run test:dashboard` | Negotiation browser fixture; Python Playwright/Chromium required |

The individual service npm commands remain supported. Source import paths have moved; update local scripts importing those internals. The API route paths, event schemas, static `/monitor/` URLs, `.env` settings, relative database locations and Docker project/volume names remain unchanged.

## Offline journey and live integration

`demo:offline` uses real HTTP routes, SQLite and deterministic domain modules with a temporary database and generated in-memory credentials. It checks initial negotiation, storm input, duplicate replay, atomic batch, injected-clock expiry, fresh recovery, dashboard files/session restrictions and persisted restart. Its expected served-priority sequence is `[9,7,6,0,9]`. It explicitly verifies that Kafka-disabled events stay queued. This command finishes and removes only its own temporary directory; it does not start a persistent demo server.

The real pipeline script instead uses the actual Kafka publisher and durable reader, real wall-clock expiry and application lifecycle. It writes uniquely named test databases in ignored `var/`. It checks 84 events for the default journey, matching consumer state and reader/service restart. Optional public weather adds another revision and additional events. These are separate proofs; offline tests do not certify broker delivery.

## Preserved local state and Docker

From this service directory, `docker compose up -d --wait` starts the existing local development Kafka broker. `docker compose -f compose.ai.yaml up -d` starts optional Ollama. The application Dockerfile now copies `dashboard/`; its entry point remains `src/server.js`. The consumer npm script now invokes `src/transport/consumer-cli.js`.

Default databases remain `var/events.sqlite` and `var/read-model.sqlite` relative to this service directory, independent of the caller's current working directory. No schema/data migration is required for consolidation. Existing credentials, models and volumes are untouched.

## Project decisions and scope

The [project blueprint](../../../docs/PROJECT_BLUEPRINT.md) records the supplied problem statement, brainstorming outcome, implementation choices, feature status and remaining gaps. Earlier plan documents retain historical file names; use this module map and current guides for current paths.

[Consolidation verification results](validation-system-consolidation.md) record the offline, Kafka, browser and container checks and their limits.
