# System consolidation

## Intent and authorization

The user approved the next step described in chat: organize the implemented ingestion, planning, agents, forecasting and dashboard modules, close their integration gaps, and provide the brainstorming output and feature decisions. This increment consolidates the existing bounded civilian implementation. It does not claim to complete the original military problem statement or production deployment.

Keep the established JavaScript runtime and current API contracts. Preserve `services/ingestion` as the deployment/data directory so existing `.env`, SQLite databases, Docker volumes, dependency installation and open guide paths remain valid. The directory name is historical; documentation and root commands must make the broader system visible.

## Design decision

Use a modular monolith with explicit source directories. Separate processes or npm workspaces would add deployment and dependency-management changes without improving the current synchronous transaction boundary. Keep `src/app.js` and `src/server.js` as composition roots.

Move existing implementations, without forwarding wrappers, into:

| Directory | Existing implementation |
| --- | --- |
| `src/contracts/` | `contracts.js` -> `events.js` |
| `src/platform/` | config, errors, shutdown |
| `src/ingestion/` | ingestion -> service, store, sample-events, scenario |
| `src/transport/` | publisher, consumer, consumer-store, consumer-cli |
| `src/planning/` | relief-world -> world, relief-planner -> planner, relief-service -> service, relief-inputs -> inputs, relief-configuration -> configuration |
| `src/agents/` | relief-negotiation -> negotiation, relief-coordination -> coordination, relief-ai -> annotations |
| `src/forecasting/` | relief-models -> demand |
| `src/integrations/` | relief-weather -> weather |
| `src/dashboard/` | monitoring |
| `dashboard/` | existing browser files from `web/` |

Preserve function exports and route URLs. Rewrite relative imports against the new locations. Adjust file-relative database roots and static asset paths explicitly. Update active documentation paths and scripts, including Python fixtures, Docker entry points, generated-contract tooling and tests. Mark historical plan paths as historical rather than silently rewriting past decisions.

The real gateway's transaction still owns accepted input, replanning, independently checked plan, revision history and mirror outbox together. Planning must not start consuming the asynchronous Kafka reader: that would change ordering/atomicity and source authority. The durable reader remains an independent delivery/replay verifier. Cross-module imports are direct; no new DI framework, event bus or barrel layers.

## Delivery slices

1. Record the feature blueprint, distinguishing user proposals, adopted choices, implementation choices and remaining gaps. A fresh reviewer checks this design and blueprint.
2. Move source/browser modules and repair all executable paths. Run existing tests, syntax and generated-contract checks. Preserve relative database locations with regression assertions.
3. Add dependency-free root npm commands that delegate to the service via `--prefix`; retain the service lockfile and no root installation requirement. Add a reproducible offline integrated journey using an isolated temporary database and generated credentials. Exercise actual HTTP routes, source update/replanning, viewer inspection, expiry and restart persistence. Disabled Kafka must remain visibly queued.
4. Update the module guide, root/service READMEs and CI invocation. Verify root commands and real browser fixtures. Run the existing Kafka journey only if a real broker is available; report availability honestly.

## Acceptance criteria

- Existing 198 tests retain their assertions and pass after relocation.
- Database defaults still resolve to `services/ingestion/var`, independent of current working directory; consumer database remains separate.
- Dashboard static files and JavaScript are available through the existing `/monitor/` routes; Python fixtures still locate the browser assets.
- Generated OpenAPI/JSON Schema stays identical unless an actual contract change is made (none planned).
- `npm test`, `npm run check`, `npm run contracts:check`, `npm run verify` and `npm run demo:offline` work from the repository root after the documented service install.
- The offline journey proves source-driven replanning, checked negotiated proposals, forecast metadata, expiry and persisted run recovery over HTTP; no external network, existing credentials or active database is used.
- Docs expose the full feature status and bounded scope without claiming historical research, production throughput, operational validation or implemented capabilities for which there is no evidence.

## Preserved constraints and limits

Five deterministic specialist policies negotiate bounded proposals before exact lexicographic optimization; independent checking retains authority. LLMs may highlight existing evidence only. Keep the current resource/revision/search/message budgets, source/admin/viewer separation, TTL conservatism, idempotency and rollback rules. Forecast evaluation remains seeded synthetic evaluation, not real-world predictive validity.

No package upgrades, new runtime dependencies, military planning features, database migrations, live operational feeds, multi-replica deployment, automatic provider polling, merges, pushes or deployment are part of this increment. Those are not implied by reorganizing the existing modules.
