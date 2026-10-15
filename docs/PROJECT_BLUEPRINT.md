# Project blueprint and feature decisions

This is the consolidated output of the recorded brainstorming and implementation plans, reconciled against the code. It distinguishes the original request from the bounded system subsequently implemented. It is not a transcript of private reasoning or a claim that every initial suggestion was adopted.

## Original problem statement

**ID:** 26250. **Title:** Air Power - Dynamic Air Operations & Resource Optimisation.

**Organization:** Ministry of Defence. **Department:** Defence Services Staff College. **Category:** Software. **Theme:** Transportation & Logistics.

The supplied statement describes the difficulty of planning and dynamically retasking air operations in a contested, rapidly changing environment. Aircraft availability, crew status, weapon loads, airspace, weather, threats and mission priorities are spread across multiple systems. The resulting lack of a common real-time decision-support framework increases planning time and produces suboptimal resource allocation. The stated technology opportunity is AI-enabled decision support, multi-source data fusion, predictive analytics and optimization.

The supplied statement included no dataset. This repository implements a fictional civilian air-relief logistics demonstrator. It covers shared logistics/data-system concepts; it does not fully satisfy the original military requirements.

## Brainstorming outcome

The user's central idea was a MAGI-inspired collection of specialists: each sees its own domain, exchanges findings with others, and participates in producing a revised plan when conditions change. The user preferred explicit algorithms and mathematical models to generate numerical evidence, with language models acting around that evidence. A single end-to-end trained black box was not the preferred approach.

The user requested JavaScript/Express ingestion, Kafka topics by domain, event-driven adaptation, a scenario showcasing changing conditions, and an end-to-end implementation. Python, LangChain, n8n, multiple database types and different forecasting/scheduling methods were suggestions to evaluate, not fixed requirements. The later explicit choice was **deterministic negotiating-agent policies**.

The adopted implementation uses:

1. Strict, authenticated domain events and durable history as a common evidence foundation.
2. Five constraint specialists: fleet, crew, weather, airport and ordinary cargo.
3. Executed peer negotiation with proposals, votes, objections, bids and counterproposals, coordinated by a supervisor.
4. A bounded exact optimizer using a checked negotiated incumbent; a separate checker validates the result.
5. New revisions after effective authorized input changes or input expiry, with persisted explanations and history.
6. A synthetic demand forecast and optional Gemma/Qwen annotations over known findings.
7. A read-only dashboard exposing current evidence, constraints, plans, negotiation and model status.

The decision to implement these numerical components in JavaScript was an implementation choice that keeps the current demonstration in one runtime. Python is used for browser verification. No Python agent runtime, LangChain, n8n or vector database was adopted.

## Architecture and data flow

```text
Authenticated source APIs
  -> strict event validation / authority / ordering / freshness
  -> one SQLite transaction:
       event history + latest evidence
       -> bound fictional inputs -> specialists -> peer negotiation
       -> exact optimizer -> independent checker
       -> revision + plan + mirrored events + durable outbox
  -> Kafka publisher -> five domain topics -> independent durable reader

Viewer session -> dashboard -> read-only evidence / simulation projections
Optional public weather refresh -> validated input -> same replanning path
Optional local language models -> allowlisted evidence highlights
Synthetic demand training -> held-out evaluation -> displayed forecast
```

Kafka distributes committed events; it is not the atomic decision coordinator. The planner reacts to explicitly bound source events inside the gateway transaction. The reader has its own durable checkpoints and does not drive the optimizer. The dashboard currently polls; it does not use push streaming.

## Feature ledger

“Implemented” means present in this bounded application with automated coverage. It does not imply production certification or a fresh live integration result on every machine.

| Capability | Status | What exists / limits |
| --- | --- | --- |
| Multi-source ingestion | Implemented | Aircraft, crew, weather, airport and ordinary cargo events; strict schemas; authenticated per-domain sources |
| Durable evidence | Implemented | SQLite history, source-specific latest state, timestamps, ordering, duplicate detection and bounded replay |
| Input quality | Implemented | Stale/expired detection, sequence gaps and visible source disagreements; sources are not silently merged |
| Kafka transport | Implemented; broker required | Five server-owned topics, transactional outbox, retries/dead work and at-least-once delivery |
| Independent reader | Implemented; broker required | Deduplication, validation/quarantine, durable checkpoints and restart replay |
| Common dashboard | Implemented | Viewer session, domain observations, freshness, delivery state, fictional world and decision inspection |
| Resource availability | Implemented for simulation | Fleet capacity/status, crew qualification/duty and maintenance validity |
| Cargo constraints | Implemented for simulation | Medical/food/water/equipment, mass, priority, cold storage and deadlines |
| Weather/airport constraints | Implemented for simulation | Fixed educational weather limits, airport opening/capacity and predefined routes |
| Optimization | Implemented for simulation | Maximize served priority, then minimize surviving assignment changes, then total arrival slots; deterministic tie breaking |
| Independent verification | Implemented | Reject invalid IDs, resource reuse, capacity, qualification, timing, expiry and objective violations; checks feasibility/arithmetic, while completed search establishes optimality |
| Autonomous negotiation | Implemented | Five stateful deterministic peers, fully connected in-process messaging, bounded rounds/messages, unanimous commitments, audited report and checked warm start |
| Supervisor/fallback | Implemented | Explicit disagreement/budget/failure states; verified deterministic fallback when policies fail |
| Dynamic replanning | Implemented | Effective authoritative bound updates, atomic batches, maintenance/TTL expiry, persisted revisions and idempotent commands |
| Configurable scenarios | Implemented, bounded | Strict fictional configuration, explicit source bindings and authority; fixed resource/slot/revision limits |
| Public weather | Implemented; explicit refresh | Open-Meteo estimates for allowlisted locations, provenance, freshness and degraded states; no automatic polling |
| Demand forecasting | Implemented on synthetic data | Seeded OLS with trend/weekly features, disjoint held-out split and mean-baseline MAE comparison |
| Multiple local LLMs | Optional integration | Gemma/Qwen via local Ollama; allowlisted finding highlights, timeouts and fallback; no authority over allocations |
| Decision explanation | Implemented | Specialist evidence, unserved reasons, negotiation messages, negotiated-versus-final outcome and revision history |
| Security/recovery | Implemented locally | Separate source/admin/viewer credentials, body/rate/budget bounds, strict validation, atomic rollback and restart recovery |
| JavaScript learning material | Implemented | Ingestion/API/Kafka walkthrough and reproducible scripts |
| Module organization/root commands | This consolidation increment | Explicit module directories and commands for the complete current application; see the module guide |
| Multi-leg/return logistics | Not implemented | Current aircraft and crew each perform at most one delivery in the toy horizon |
| Real fleet/crew integrations | Not implemented | Source API is usable, but no operational source adapters or real fleet validation are included |
| Learned maintenance/arrival prediction | Not implemented | Maintenance is a constraint/expiry input; arrival slots are route arithmetic |
| Real demand dataset/model validity | Not established | Synthetic evaluation does not demonstrate real-world forecast performance |
| Production-scale optimization | Not implemented | No large-fleet solver or operational benchmark; bounded search only |
| Distributed agent processes | Not implemented | Fully connected protocol runs synchronously in-process; no independent network services |
| Production deployment | Not established | No multi-replica database/limiter, managed secrets/HA, operational certification or demonstrated SLO |
| Combat-specific requirements | Not implemented | Adversary threat assessment, weapons allocation, contested-airspace tactics and military mission retasking are outside the built demonstrator |

## Deterministic algorithms and model choices

The optimizer uses bounded exact enumeration with lexicographic objectives. Negotiation produces a feasible incumbent; completed exact search may refine it. Budget-limited feasibility is reported separately from proven optimality. Constraints cannot be negotiated away. Prior assignments influence plan stability, rather than becoming irrevocable reservations across revisions.

The demand model fits four features (intercept, trend, weekly sine and cosine) with ordinary least squares and pivoted Gaussian elimination. Its training/evaluation artifact records the seed, feature definition, train/test days and errors. The random held-out split measures this synthetic generator; it is not a chronological backtest. The displayed forecast does not automatically rewrite request priorities or planner inputs.

CPM, job-shop scheduling, CP-SAT/MILP, learned demand/maintenance/arrival models and alternative multi-objective solvers were possible approaches in the initial discussion. They are not implementations in this repository. Current slot scheduling is a small bounded allocation problem.

## Selection demonstration

Use a fictional hub delivering medical supplies, food and water to a clinic and shelter. Show:

1. An initial verified plan, resource constraints, priorities, forecast and real peer negotiation trace.
2. A source-authenticated storm update reducing feasible deliveries and triggering a new checked revision.
3. A repeated event producing a duplicate receipt without an extra revision.
4. A batch updating two locations atomically; stale/unbound inputs remain visible without changing the plan.
5. Input expiry making the evidence unusable and triggering a conservative replanning revision.
6. Fresh recovery observations restoring feasible deliveries, with explanations of changed assignments.
7. Separate viewer access and persisted recovery after application restart.
8. When Docker/Kafka is available, committed outbox delivery and the independent reader catching up and recovering across restart.

The existing scripted scenario also demonstrates aircraft maintenance, airport closure and cargo-demand changes. Public weather and real local model calls are optional, separately identifiable integrations. A demo must distinguish those from generated scenario events.

## Current implementation bounds

The planning world allows at most three aircraft, three crews, three airports, two routes, five ordinary requests and three departure slots. Logical slots/ticks and wall-clock TTL are separate. Revision/expiry limits end a run rather than allowing unbounded recomputation. Negotiation defaults to four rounds per request and at most 512 directed messages; configured bounds remain strict. These limits make the current demonstration reproducible; they do not support a production-scale claim.

## Remaining work and acceptance evidence

This consolidation finishes module discoverability, root entry points and a reproducible isolated offline journey. The unit/HTTP suite, syntax/contracts checks and browser fixtures verify it. Real-broker, public-weather and local-model checks need their actual dependencies; an unavailable dependency is reported as untested, never passed.

Further general logistics development would need separately specified acceptance criteria for multi-leg scheduling, larger optimization benchmarks, additional civil source adapters, chronological forecast evaluation, deployment/recovery tooling and operator workflows. No selection probability or novelty claim is established by the present tests.

## Source records

- [Ingestion design](logistics-ingestion-design.md)
- [Monitoring plan](logistics-monitoring-plan.md)
- [Initial relief engine plan](civilian-relief-engine-plan.md)
- [Dynamic extensions plan](civilian-dynamic-extensions-plan.md)
- [Autonomous negotiation plan](civilian-negotiation-plan.md)
- [Consolidation design](superpowers/specs/2026-10-15-system-consolidation-design.md)
- [Detailed engine guide](../services/ingestion/docs/CIVILIAN_ENGINE_GUIDE.md)
- [Dynamic guide](../services/ingestion/docs/DYNAMIC_CIVILIAN_GUIDE.md)
- [Negotiation guide](../services/ingestion/docs/AUTONOMOUS_NEGOTIATION_GUIDE.md)
