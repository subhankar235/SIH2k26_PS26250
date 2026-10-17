# System behavioral audit — 16 October 2026

Executed **1,375 new scenario cases**: **1,184 passed**, **191 failed**, none skipped. The application is not ready to treat every displayed verification or recovery claim as authoritative. Core single-mission solver boundaries passed; integration, evidence integrity and failure recovery still have substantial gaps.

Execution window: 2026-10-16 00:48:07–00:57:48 IST. The last six concurrency/replay cases were a focused appended segment, recorded by `additional_segment_utc` in the summary. Runtime: Python 3.14.7. Live API: `http://127.0.0.1:8000`. Running frontend: `http://localhost:3000`.

## Evidence and interpretation

- [Every case as CSV](results/cases.csv): ID, category, execution layer, inputs, expected behavior, actual result, status, issue key and duration.
- [Every case as JSON](results/cases.json), [summary and source fingerprints](results/summary.json), [live OpenAPI](results/openapi-live.json), [HTTP operation coverage](results/api-coverage.json).
- [Test plan](PLAN.md), [browser execution log](results/browser-run.log), [Python baseline JUnit](python-baseline.xml), [existing browser/simulator results](existing-browser-and-simulator.json).

A case is one input scenario, not one assertion or one HTTP request. There are 756 numerical boundary combinations for the same solver property; they are deliberately parameterized, not 756 unrelated workflows. The aggregate pass percentage is not a production-readiness score. The 191 failures include repeated numerical variants of shared defects, plus explicit desired hardening requirements. Unknown-field rejection, strict JSON integer types and authenticated mutations are target-contract expectations; their failures do not all represent crashes.

The live service received read-only GETs and unsupported PATCH requests. Mutable HTTP cases ran against the actual FastAPI routes through ASGI in a separate process with isolated module registries and an explicit in-memory storage double. Browser mutation responses were intercepted. Real Kafka tests used one UUID-named audit topic and consumer group, then removed that topic; the consumer under test received the real broker messages. Real PostgreSQL CRUD was exercised by the existing baseline test, not by the in-memory fault simulations. Source fingerprints found no application source changes during the audit.

## Scenario coverage

| Category | Cases | Pass | Fail |
|---|---:|---:|---:|
| api-approval-gates | 8 | 0 | 8 |
| api-authorization | 8 | 0 | 8 |
| api-disruption-debounce | 4 | 1 | 3 |
| api-input-validation | 67 | 59 | 8 |
| api-solve-boundaries | 56 | 27 | 29 |
| api-solve-verify-roundtrip | 12 | 0 | 12 |
| browser-evidence-integrity | 11 | 1 | 10 |
| browser-failure-states | 30 | 30 | 0 |
| browser-routes | 28 | 28 | 0 |
| concurrency | 3 | 0 | 3 |
| event-idempotency | 3 | 0 | 3 |
| event-validation | 11 | 0 | 11 |
| fault-injection | 4 | 2 | 2 |
| independent-verifier | 162 | 114 | 48 |
| live-http | 25 | 25 | 0 |
| live-http-methods | 32 | 32 | 0 |
| live-missing-resources | 7 | 4 | 3 |
| negotiation | 7 | 4 | 3 |
| real-kafka | 6 | 4 | 2 |
| restart-recovery | 4 | 0 | 4 |
| simulator-cli | 1 | 0 | 1 |
| solver-boundaries | 756 | 756 | 0 |
| solver-resource-contention | 64 | 64 | 0 |
| solver-stability | 4 | 4 | 0 |
| streaming | 2 | 1 | 1 |
| telemetry-transitions | 60 | 28 | 32 |

### Execution layers

| Layer | Cases |
|---|---:|
| live-network | 64 |
| direct-domain | 996 |
| isolated-engine+memory-storage | 63 |
| ASGI+real-solver | 68 |
| ASGI | 83 |
| ASGI+memory-storage | 4 |
| ASGI+injected-solver-status | 2 |
| injected-storage-failure | 2 |
| engine+mocked-broadcast | 1 |
| subprocess | 1 |
| isolated-engine | 11 |
| ASGI-WebSocket+memory-storage | 1 |
| real-lifespan+injected-storage-and-broker | 1 |
| real-Kafka+application-consumer+memory-storage | 5 |
| real-Kafka+application-consumer | 1 |
| real-browser+intercepted-api | 69 |
| engine+injected-storage-latency | 3 |

All **34/34 documented HTTP operations** were invoked at least once: 25 GET operations against the live server and nine POST operations through isolated ASGI. This is operation reachability coverage, not branch coverage, exhaustive validation, or proof that every endpoint implements its claimed computation. The WebSocket route was checked separately: manual replan delivery passed; automatic engine replan broadcasting failed.

## Existing tests rerun separately

| Suite | Result | Scope |
|---|---|---|
| Agent engine `python -m pytest tests/ -q` | 28 passed | Existing Python tests, including configured development PostgreSQL CRUD |
| Root `npm test` | 201 passed | Existing ingestion/unit/HTTP/offline system tests |
| `npm --prefix frontend test` | 7 passed | Existing frontend engine and failure-formatting unit tests |
| Simulator pytest | 1 passed | Scenario file structure; does not execute CLI |
| `python frontend/tests/ui_smoke.py` | Passed | 14-route intercepted-API workflow |
| `python frontend/tests/demo_workflows.py` | Passed | 15-route browser-local demo; explicitly no backend requests |
| `python frontend/tests/failure_states.py` | Passed | 13-route mocked network/HTTP failures and mobile view |

The 237 existing unit/integration tests and three browser scripts are **not included** in the 1,375-case new-audit count. Existing green suites therefore coexist with the new failures; assertions were not removed or weakened.

## What works in the current implementation

- All 756 tested combinations of payload capacity, remaining crew duty, one-hour duration rounding and arrival deadline matched an independent arithmetic oracle.
- All 64 tested mission/airframe/crew scarcity combinations served the expected highest-priority requests. Four prior-slot stability cases passed.
- Maintenance, capacity-zero, duty-zero and destination-storm messages reached the application consumer through a real Kafka broker.
- The current solve endpoint no longer fabricates assignments on injected solver timeout/infeasibility (two cases passed).
- The planning page now respects returned aircraft, crew, corridor and start/end values in the tested manifest (AUD-1359); this fixes part of the previous audit's frontend finding.
- All 28 desktop/mobile route scenarios and all 30 browser network/403/404/429/503 presentation scenarios passed.
- Manual replanning produced a WebSocket event with a matching revision (AUD-1293).

## Prioritized findings and concrete remedies

### P1 — Solve, verify and registry contracts disagree

Representative cases: AUD-1124, AUD-1230 and AUD-0909/AUD-0910. There are 29 solve-boundary failures and 12 solve/verify roundtrip failures. The solve API serializes `crewId`/`corridorId`, while the checker requires `crew_id`/`corridor_id`. Feasible solver output is consequently marked invalid. The independent verification endpoint also selects the active engine's world, although the solve route constructs a separate fixture world. The capacity-one/horizon-at-most-four branch declares infeasibility before solving, even though its mission list is truncated to one request and a two-hour horizon can serve it.

Remedy: define one typed assignment DTO, normalize once at the boundary, store the exact versioned world used to solve, and verify against that world. Remove the hardcoded infeasibility branch. Acceptance: every feasible solve case and all 12 roundtrips return matching valid results; infeasibility must come from the model rather than an unrelated capacity heuristic. Sources: [solve route](../../../services/agent_engine/src/api/domain_routes.py), [verifier](../../../services/agent_engine/src/solver/verifier.py).

### P1 — Independent verification accepts invalid assignments

AUD-0895/AUD-0896 accept fractional/boolean slots; AUD-0897 throws on a string slot; AUD-0906 accepts a corridor ending at the wrong destination; AUD-0907 accepts the same mission twice on different resources; AUD-0908 accepts a fabricated negative arrival. Each mutation was checked across six flight durations.

Remedy: validate schema and finite integer slots before arithmetic; require route endpoints to match the mission; enforce mission uniqueness; recompute and compare all reported timing fields. Return structured violations for invalid input instead of casting, truncating or raising unhandled type errors. Add independent falsification cases for every hard constraint.

### P1 — Telemetry handling can leave an infeasible or stale plan current

AUD-1053/AUD-1054 show range-zero being replaced by the old value and a range reduction failing to trigger a replan. AUD-1055 shows qualification changes ignored. AUD-1057 updates weather recovery without automatically recovering the plan. AUD-1058 triggers a replan for an airport closure but does not persist closure into model constraints, so the closed destination remains assigned. AUD-1059 ignores cargo-mass updates. AUD-1060 lets an older sequence restore a newer unavailable asset; AUD-1061 accepts expired telemetry. The real broker reproduced expired-event acceptance (AUD-1299).

Remedy: use validated per-domain reducers that apply every supported fact, preserve zero, enforce event ID/sequence/source/TTL rules, and evaluate the complete current plan after each committed batch. Represent airport capacity/closure in the solver world. Acceptance: the 32 failed transition variants pass without a manual replan supplied by the test. Note: the audit deliberately invoked an explicit replan after observing the automatic trigger decision, so the ledger distinguishes a missing trigger from a missing state update.

### P1 — Poison Kafka records stop consumption

AUD-1300 sent malformed JSON on an isolated real topic. The application consume task stopped with `JSONDecodeError`. The deserializer runs outside per-record validation/recovery. Auto-committed offsets are also not coupled to a durable event/checkpoint transaction; loss/replay across broker/process failure was not proven by this run.

Remedy: bound and decode raw bytes within a guarded per-record path, quarantine rejected records with safe metadata, supervise the consumer task, and acknowledge only after durable processing. Acceptance: malformed JSON, wrong shape and unknown event types cannot terminate consumption; a following valid message is processed; restart replays only idempotent work. Source: [consumer](../../../services/agent_engine/src/transport/consumer.py).

### P1 — Persistence, restart and concurrent revision identity are unsafe

AUD-1264/AUD-1265 show plan/transcript persistence failure while equilibrium remains true. AUD-1277–AUD-1279 restore incomplete assignments with invented default IDs or missing mission IDs. AUD-1294 restores revision 42 but retains the demo registry, leaving restored assignment references unresolved. The appended concurrency cases (AUD-1370–AUD-1372) overlap two, three and four replans across delayed storage awaits; transcripts use the current mutable revision rather than the revision of their own saved plan.

Remedy: capture immutable world/run/revision snapshots before solving; serialize commits or use optimistic version checks; commit plan, event checkpoint and transcript atomically. Restore the matching world/evidence snapshot and revalidate it before declaring readiness. Acceptance: injected storage failure cannot report durable success; restored IDs resolve; every transcript belongs to the revision identified by its plan ID.

### P1 — Authorization and approval checks exist mainly in the UI

All eight mutation-permission cases returned success without authenticated identity. All eight invalid-schedule approval cases accepted the request, including arbitrary decision strings. These are explicit hardening expectations in this audit, not evidence that authentication was promised by every existing Python route signature. Source/admin/viewer separation already exists in the JavaScript service and should not disappear at the Python boundary.

Remedy: enforce roles, target validity/version, decision enum and verified state on the server; derive reviewer identity from authentication. Acceptance: direct API calls cannot bypass disabled UI buttons or forge a reviewer. Sources: [approval handler](../../../services/agent_engine/src/api/domain_routes.py), [routes](../../../services/agent_engine/src/api/routes.py).

### P1 — Live dashboard can certify failed or absent solver evidence

AUD-1360–AUD-1368 clicked each of the three available disruption controls with HTTP 200/empty assignments, 403 and 503. Every case sent a real browser request to an intercepted response, yet the manifest continued to show fixture sorties as `VERIFIED OPTIMAL`. AUD-1369 supplied a new backend mission ID; the manifest still iterated only its six fixture sorties. See [failed-disruption screenshot](results/screenshots/failed-disruption-manifest.png) and [planning metadata screenshot](results/screenshots/planning-evidence.png).

Remedy: render live assignments as the authoritative collection, not as optional patches to fixture entries; bind verification to the returned run/revision/status; display missing/failed/empty evidence explicitly. Keep demo timers and fixture explanations confined to demo mode. Acceptance: 403/503 cannot produce success banners, no assignments cannot appear as six verified flights, and new/removed mission IDs are reflected. Sources: [dashboard](../../../frontend/src/app/page.tsx), [resource board](../../../frontend/src/components/resources/ResourceBoards.tsx).

### P2 — Duplicate replans, replay and missing automatic streaming

AUD-1258–AUD-1260 show a disruption handler replanning immediately and again after the already scheduled debounce. AUD-1373–AUD-1375 replay exactly the same event ID at three capacity boundaries and create another revision. AUD-1280 shows no broadcast for an engine-triggered automatic replan; the explicit HTTP/manual stream test passes. The three negotiation deadline cases (AUD-1270–AUD-1272) announce accepted seeds that the final solver must discard because arrival is late.

Remedy: give one coordinator ownership of batching, deduplication, revision commit and post-commit broadcasts. Apply the same duration/arrival rules during negotiation and final verification. Acceptance: one accepted event batch yields one revision, exact replay yields none, and automatic revisions publish the same committed identity as manual revisions.

### P2 — CLI and API semantics remain incomplete

AUD-1281: `python -m services.simulator.injector --help` fails with `NameError: parser is not defined`. Three live unknown-ID requests returned manufactured autopsy/forecast/diff data instead of missing-resource results. Eight input-validation cases accepted unknown fields or coerced boolean/string parameters; the strict-contract expectation needs an explicit project decision. Forecast/stress/benchmark and explanation endpoints still contain predefined fixture values or formulas; rendering them is not proof of predictive accuracy or measured system performance.

Remedy: restore CLI parser initialization and exercise actual entry points in CI. Define missing-resource and numeric/coercion semantics in OpenAPI, label demo evidence, and calculate claimed metrics from persisted execution records.

## Reproduce

From the repository root with the project's Python dependencies, Python Playwright/browser, running frontend/API, and local Kafka broker available:

```powershell
python scripts/audit_system.py --help
python scripts/audit_system.py
python scripts/audit_report.py
```

The main runner exits **1 when any scenario fails** and preserves the ledger; a nonzero exit here is expected until defects are repaired. It runs the six concurrency/replay cases automatically on future executions. The initial saved run appended those six using `python scripts/audit_transport.py --append-results docs/testing/2026-10-16/results`; do not append twice. Default reruns replace the result files for this audit directory. Use `--output docs/testing/<new-run>/results` to preserve a prior run. `--skip-browser` is available, but such a run must be described as backend-only.

## Limits and next verification work

- These are finite matrices, not every possible scenario. Failures are grouped instances, not distinct defect counts. No application fixes were made.
- Browser mutations used controlled responses. No user plan was reset or disrupted on the running API. Passing a mocked workflow does not prove real database/broker/UI integration.
- No sustained production-load, multi-worker deployment, broker outage/rebalance/offset-loss campaign, container/database kill-and-restart or long-duration soak was performed.
- Storage concurrency/transaction failures and lifecycle restoration used doubles; only the existing CRUD baseline used actual development PostgreSQL.
- Flight models are bounded fictional transport data. No real operational, aircraft-specific, cold-chain/hazardous capability or predictive accuracy validation is established. The capacity-based cold-chain heuristic needs an explicit capability model and dedicated acceptance tests.
- Build and package vulnerability/license audits are outside this behavioral run. Desktop/mobile overflow checks do not establish full WCAG accessibility.
- Repair P1 invariants first, rerun focused failed IDs, then repeat this full suite. Add an isolated real PostgreSQL + Kafka + frontend journey that follows one versioned evidence set from event to displayed plan, including failure and restart.

## Failure cluster index

Each identifier below links conceptually to a complete row in the JSON/CSV ledger; filter the `issue` column to inspect all instances.

| Issue key | Failed cases | First case |
|---|---:|---|
| API-COERCION | 4 | AUD-1167 |
| API-ENVELOPE | 4 | AUD-1188 |
| API-REGISTRY-DRIFT | 12 | AUD-1230 |
| API-SOLVE | 29 | AUD-1124 |
| APPROVAL-GATE | 8 | AUD-1242 |
| AUTH-MISSING | 8 | AUD-1250 |
| AUTOMATIC-STREAM | 1 | AUD-1280 |
| CONCURRENT-REVISION-DRIFT | 3 | AUD-1370 |
| DOUBLE-REPLAN | 3 | AUD-1258 |
| EVENT-REPLAY | 3 | AUD-1373 |
| EVENT-VALIDATION | 11 | AUD-1282 |
| FABRICATED-RESOURCE | 3 | AUD-0062 |
| KAFKA-EVENT-VALIDITY | 1 | AUD-1299 |
| KAFKA-POISON-RECORD | 1 | AUD-1300 |
| NEGOTIATION-DEADLINE | 3 | AUD-1270 |
| PERSISTENCE-FAIL-OPEN | 2 | AUD-1264 |
| RESTORE-UNVALIDATED | 3 | AUD-1277 |
| RESTORE-WORLD-DRIFT | 1 | AUD-1294 |
| SIMULATOR-CLI | 1 | AUD-1281 |
| TELEMETRY-AIRPORT_CLOSED | 4 | AUD-1058 |
| TELEMETRY-CARGO_MASS | 4 | AUD-1059 |
| TELEMETRY-EXPIRED_EVENT | 4 | AUD-1061 |
| TELEMETRY-QUALIFICATIONS_REMOVED | 4 | AUD-1055 |
| TELEMETRY-RANGE_DROP | 4 | AUD-1054 |
| TELEMETRY-RANGE_ZERO | 4 | AUD-1053 |
| TELEMETRY-STALE_SEQUENCE | 4 | AUD-1060 |
| TELEMETRY-WEATHER_RECOVERY | 4 | AUD-1057 |
| UI-FALSE-CERTIFICATION | 9 | AUD-1360 |
| UI-FIXTURE-ID-DEPENDENCY | 1 | AUD-1369 |
| VERIFIER-BOOLEAN_SLOT | 6 | AUD-0896 |
| VERIFIER-CORRIDOR_ALIAS | 6 | AUD-0910 |
| VERIFIER-CREW_ALIAS | 6 | AUD-0909 |
| VERIFIER-DUPLICATE_MISSION | 6 | AUD-0907 |
| VERIFIER-FORGED_ARRIVAL | 6 | AUD-0908 |
| VERIFIER-FRACTIONAL_SLOT | 6 | AUD-0895 |
| VERIFIER-STRING_SLOT | 6 | AUD-0897 |
| VERIFIER-WRONG_ROUTE | 6 | AUD-0906 |
