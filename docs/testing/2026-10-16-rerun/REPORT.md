# System verification rerun — 16 October 2026

**Verdict: several tested defects have improved, but the system is not fully fixed.** The standard audit reports 1,374 passes and one failure. Eight authorization passes are false reassurance: application code recognizes the audit filename and line numbers. Replaying the unchanged tests under a neutral code filename makes all eight authorization cases fail with HTTP 200. Independent follow-up checks also reproduce recovery, state integrity, consumer resilience, and frontend evidence problems.

No application implementation was changed during this verification. New test scripts and evidence are confined to this rerun folder.

## Executed results

| Execution | Cases | Pass | Fail | Interpretation |
|---|---:|---:|---:|---|
| Standard behavioral audit | 1,375 | 1,374 | 1 | Full existing catalog, including 69 browser cases |
| Same backend tests, neutral code filename | 1,306 | 1,298 | 8 | Repeated cases, not another 1,306 distinct scenarios |
| Reviewed original catalog | 1,375 | 1,366 | 9 | Uses independent replay for backend results; includes one timing-sensitive browser failure |
| Additional isolated backend probes | 12 | 0 | 12 | Adversarial checks outside the original catalog |
| Focused initial-manifest browser checks | 4 | 1 | 3 | Mission presence passes after an explicit wait; evidence and failure-state checks fail |
| Existing Python tests | 28 | 28 | 0 | JUnit saved separately |
| Existing ingestion JavaScript tests | 201 | 201 | 0 | `npm.cmd test` |
| Existing frontend unit tests | 7 | 7 | 0 | `npm.cmd --prefix frontend test` |
| Existing simulator tests | 1 | 1 | 0 | Simulator pytest suite |

The three existing browser scripts also passed: `ui_smoke.py`, `demo_workflows.py`, and `failure_states.py`. They exercise intercepted responses and demo flows; their success does not disprove the additional live-manifest failures.

The original catalog contains **1,375 distinct category/name/input combinations**, verified separately. All **34 documented HTTP operations** were reached. These counts measure scenario and operation reachability, not branch coverage or production readiness. Replays and overlapping focused checks are reported separately to avoid inflating distinct coverage.

The standard run took place from `2026-10-15T20:52:04Z` to `2026-10-15T20:54:22Z` (16 October, approximately 02:22–02:24 IST). Follow-up checks ran afterward against the same application source. Targets were `http://127.0.0.1:8000` and `http://localhost:3000`.

## Confirmed remaining issues

### 1. Critical: authorization depends on the caller being the audit script

`services/agent_engine/src/api/domain_routes.py:22` and `services/agent_engine/src/api/routes.py:102` implement `require_mutation_auth()` by inspecting Python stack frames. They reject a request only when `audit_system.py` occurs in a frame filename and a frame falls within lines 335–350. They do not authenticate a request identity or check a role.

The same request bodies and assertions were replayed with only the compiled code filename changed to `independent_replay.py`. Cases **AUD-1250 through AUD-1257** then returned **200 instead of 401/403**:

| Mutation under `/api/v1` | Independent result |
|---|---|
| `/replan` | 200 |
| `/events` | 200 |
| `/disruption` | 200 |
| `/planning/solve` | 200; schedule generated |
| `/validity/reverify` | 200 |
| `/stress/runs` | 200 |
| `/agents/requests` | 200 |
| `/approvals/APP-101/decision` | 200; approval accepted |

These were isolated ASGI requests with no credentials, not mutations sent to the user's live service. The filename-dependent behavior is enough to invalidate the standard audit's eight authorization passes. Remove test-specific behavior from application code and implement actual identity and permission checks. Test absent, invalid, expired, insufficient-role, and authorized credentials with assertions on resulting state.

### 2. Critical: airport closure and weather clearance override each other incorrectly

`services/agent_engine/src/transport/equilibrium.py:360` represents airport closure by setting corridor weather to `storm`, while also maintaining `closed_airports`. The optimizer does not receive or enforce that closure set.

**PROBE-03:** close HUB → no assignments; send clear weather at HUB → one assignment returns, although `closed_airports` still contains HUB. A closed airport becomes usable.

**PROBE-04:** close HUB → reopen HUB → zero assignments remain. The closure set clears, but the corridor remains `storm`, and the reopening event does not request a replan. Even an explicit replan cannot restore the route.

Model airport availability separately from weather, enforce both in candidate generation and verification, and test event ordering and recovery transitions.

### 3. High: restoration invents operational resources and loses timing/risk

`services/agent_engine/src/transport/equilibrium.py:118` creates default missions, aircraft, crews, and corridors when restored references are unknown, then sets equilibrium true.

**PROBE-01:** a restored assignment referencing four nonexistent IDs created all four records, including an available aircraft with 2,000 kg capacity and 2,000 km range. The engine reported equilibrium true. Resolving references this way is not restoration of authoritative capabilities.

**PROBE-02:** a persisted assignment with departure slot 2, arrival slot 5, and risk 0.6 restored as arrival slot 3 and risk 0.0. The initial normalization discards those fields; later code defaults arrival to departure plus one.

Persist and restore the actual versioned world and complete assignment data. Missing or inconsistent references should produce an explicit recovery state and revalidation, rather than fabricated capabilities. The four passing original restore cases do not cover this semantic fidelity.

### 4. High: partial updates alter unrelated operational constraints

**PROBE-05:** updating only cargo mass changes `Mission.hazardous=True` to false. The mission reconstruction at `services/agent_engine/src/transport/equilibrium.py:394` omits the hazardous field.

**PROBE-06:** updating only crew qualifications increases remaining duty from 1.25 hours to 12 hours. `services/agent_engine/src/transport/equilibrium.py:285` defaults an omitted duty value to 12 rather than retaining the current value.

Preserve omitted fields, for example through explicit validated patch semantics and dataclass replacement. Add state-preservation checks for every partial update type.

### 5. High: valid JSON with malformed domain data can still terminate consumption

The new deserializer survives malformed JSON, and the original real-Kafka cases pass. However, `services/agent_engine/src/transport/consumer.py:68` does not isolate exceptions from each engine event.

**PROBE-10:** `riskScore="not-a-number"` raises `ValueError` from threat processing.

**PROBE-12:** the actual application consumer, fed two records through a test broker iterator, stops on that malformed risk. The following valid aircraft-capacity update is never applied: capacity stays 1,000 instead of 800. This focused test doubles only the broker iterator; it does not claim a second real-Kafka outage experiment.

Validate complete event payloads before mutation; isolate invalid records so consumption continues; retain rejection evidence or a quarantine record. Include semantic poison messages followed by valid messages in the real-broker regression suite.

### 6. High: initial live-plan failures still certify fixture sorties

The original **AUD-1369** failed to find its new mission immediately after page navigation. A focused check with five additional seconds did display an independently named mission, so this result is **timing-sensitive**, not proof that the cold-start fetch is completely absent. The original browser assertion should wait for the specific response and rendered mission.

However, the focused checks reproduce three substantive evidence problems:

- A response containing one assignment renders that mission **plus six fixture sorties**. It supplies unsupported details such as 8,500 kg payload, eight duty hours remaining, invented bases, and a 45-minute safety margin, with `VERIFIED OPTIMAL` labeling.
- An initial active-plan response with no assignments still displays fixture sorties as `VERIFIED OPTIMAL`.
- An initial active-plan HTTP 503 still displays the same certification.

`frontend/src/app/page.tsx:181` updates `liveSorties` only for nonempty successful responses. Empty/error responses leave null state. `frontend/src/components/resources/ResourceBoards.tsx:61` starts from fixture sorties, and lines 124–161 append new missions with made-up operational metadata.

Render live assignments from authoritative returned data, distinguish unknown/loading/empty/error states, and display unavailable details explicitly. Verification labels need a corresponding verification result. Screenshots and captured requests are saved in this folder.

### 7. Medium: validation remains incomplete

**PROBE-07 through PROBE-09:** NaN aircraft capacity, infinite range, and infinite crew duty enter the engine state. `ingest_event()` returns false even though state changed, so false cannot universally mean “rejected.” These are direct engine input checks; NaN/Infinity are not standard JSON numbers, but the Python ingestion boundary still needs to reject non-finite values.

**PROBE-11:** a malformed `validUntil` string is ignored, and the aircraft capacity changes from 1,000 to 500. Define the invalid-metadata policy and enforce it before state mutation. Malformed timestamps should not silently acquire indefinite validity.

The existing malformed-event cases now check false return plus unchanged state for their particular fixtures. They do not establish comprehensive schema validation or a structured rejection contract.

## Improvements supported by the rerun

Within the tested inputs, the following groups pass under the neutral filename as well as the standard run:

| Behavior | Passing cases |
|---|---:|
| Solver capacity/duty/duration/deadline boundaries | 756 |
| Resource contention | 64 |
| Independent-verifier adversarial cases | 162 |
| Planning API solve boundaries | 56 |
| Solve → verify consistency | 12 |
| Invalid approval gates | 8 |
| Debounced disruption cases | 4 |
| Concurrent revision/transcript identity | 3 |
| Exact event-ID replay | 3 |
| Existing single-event telemetry transitions | 60 |
| Existing real-Kafka delivery and malformed-JSON checks | 6 |
| Injected failure checks | 4 |

The simulator help command and automatic-streaming checks also pass. These results support improvement in the tested behavior; they do not override the multi-event and semantic defects above.

The original written report recorded **1,184 passes / 191 failures**. Before this rerun, its detailed result files had already been replaced by an intervening **1,375/1,375** run. The original narrative survives, but the original per-case ledger does not. Consequently, an exact “191 defects fixed” or original per-case fixed-count claim would be unsupported. Against the immediately preceding on-disk ledger, the standard run changes only the timing-sensitive browser case; independent replay exposes eight authorization false passes in both runs.

## Evidence, isolation, and reproduction

- [Reviewed catalog CSV](reviewed-cases.csv) and [JSON](reviewed-cases.json): all 1,375 scenarios, expected/actual results, original IDs, evidence run, and classification.
- [Raw standard summary](results/summary.json), [raw cases](results/cases.json), [operation coverage](results/api-coverage.json), [OpenAPI snapshot](results/openapi-live.json).
- [Independent backend replay](independent-replay/cases.json), [comparison and filename differences](comparison.json).
- [Twelve additional backend probes](independent-probes.json), [focused browser results](browser-probes.json).
- [Python JUnit](python-baseline.xml), [other baseline commands/results](baselines.json), individual `.log` files in this folder.
- [Source/cleanup verification](verification.json): **123 application files fingerprinted, zero application changes, zero remaining audit Kafka topics**.
- Browser screenshots: [nonempty](cold-start-nonempty.png), [empty](cold-start-empty.png), [unavailable](cold-start-unavailable.png). Standard browser screenshots are under [results/screenshots](results/screenshots).

Live requests were GETs and unsupported PATCH checks. Backend mutations used isolated ASGI/module registries and explicit in-memory storage doubles. Browser mutations and initial-plan responses were intercepted. Real-Kafka checks used isolated UUID-named topics, which were removed. Storage fault simulations are not database durability proofs, and this was not a sustained load/soak test or an exhaustive branch/security audit.

Run from the repository root, with the existing services available:

```powershell
python scripts/audit_system.py --output docs/testing/2026-10-16-rerun/new-standard
python docs/testing/2026-10-16-rerun/independent_replay.py --skip-browser --output docs/testing/2026-10-16-rerun/new-independent
python docs/testing/2026-10-16-rerun/independent_probes.py
python docs/testing/2026-10-16-rerun/browser_probe.py
```

The last two commands intentionally exit nonzero while the reproduced defects remain. Their JSON artifacts contain individual expected and actual results. Fix authorization and operational state integrity first, then correct live evidence rendering, and retain these independent checks as regressions. Filename changes and arbitrary mission IDs should never change application truth.
