# Civilian relief simulation engine

## Intent and boundaries

Build a complete educational relief-cargo simulation connected to the existing event gateway, Kafka outbox/reader and browser. This is a separate fixed fictional scenario, not an optimizer over real gateway observations. No weapons, adversaries, tactical threat scoring, military missions, targeting, combat-engine implementation instructions or conversion guide are included. Aircraft are fictional capacity containers; there is no flight navigation, fuel model or certification claim.

The user has authorized the noncombat alternative and autonomous implementation, including routine design choices. The detailed guide will document this system, not the requested combat engine.

## Capability map and order

| Module | Responsibility | Depends on |
| --- | --- | --- |
| relief-world | Sealed fictional scenario and ordered perturbations | Existing typed event contracts |
| relief-planner | Specialist constraint reports, bounded exact search and independent checker | World contract |
| relief-models | Seeded synthetic demand regression/evaluation; local-model evidence selection | Specialist report contract |
| relief-service | Atomic event/state persistence, revision guards, command idempotency, background model annotation | Above modules, EventStore |
| relief-ui | Read-only world/plan/revision/agent/model inspection | Viewer session API |
| relief-guide | Reproducible setup, full implementation walkthrough, model/dataset/evaluation/runbook | Verified implementation |

## World contract

`{version:1,simulation:true,runId:UUID,revision:0..20,tick:0..10,policy,aircraft,crews,airports,weather,routes,requests,demandHistory}`. The world is created only by `createReliefWorld({runId,now})`; no endpoint accepts arbitrary worlds, objectives, routes or risk models. All IDs start `SIM-`. Maximum 3 aircraft, 3 crews, 3 airports, 2 routes, 5 requests, 3 departure slots, 31 demand-history points.

- policy: `{slots:[0,1,2],slotMinutes:30,minVisibilityM:3000,maxWindSpeedMps:15}`. Fixed educational limits, never aviation guidance.
- aircraft: `{id,airportId,capacityKg,coldStorage,status,validThroughTick}`; available/maintenance/unavailable.
- crews: `{id,status,qualifications:['relief-pilot'],fromSlot:0,toSlot:4,validThroughTick}`; available/rest/unavailable.
- airports: `{id,status,arrivalsPerSlot,departuresPerSlot,validThroughTick}`; open/restricted/closed.
- weather: `{airportId,windSpeedMps,visibilityM,condition,validThroughTick}`.
- routes: `{originId,destinationId,durationSlots:1}`.
- requests: `{id,category,massKg,originId,destinationId,temperatureControlled,priority:1..5,deadlineSlot:1..4,validThroughTick}`. Categories medical/food/water/equipment only.
- demandHistory: `{day:integer,demand:nonnegative integer}[]` generated from a published fixed synthetic seed.

Each aircraft and crew performs at most one delivery in the toy horizon; no multi-leg routes or return logistics. A validThroughTick less than current tick is expired. Logical slots/ticks are explicitly separate from the wall clock.

## Planner and model interfaces

`optimizeReliefWorld(world,{previousAssignments=[],nodeLimit=100000}={})` returns `{status:'optimal'|'feasible_budget',assignments,unserved,objective,diagnostics,agentReports}`. Assignment `{requestId,aircraftId,crewId,departureSlot,arrivalSlot}`. Unserved `{requestId,reasonCodes:string[]}`. Objective lexicographic: maximize served priority; then minimize changed surviving prior request assignments; then minimize total arrival slots. Tie-break stable IDs. Node budget is a deterministic upper bound, not a wall-clock claim. A budget-limited feasible result is never labelled optimal. Empty plans are valid and explanatory.

Reports are `{agentId:'fleet'|'crew'|'weather'|'airport'|'cargo',findings:[{id,code,message,entityIds:string[]}],eligibleIds:string[]}`. Every eligibility and rejection reason is grounded in the sealed world. Specialist reports feed a supervisor/search, not an all-to-all LLM chat. Search diagnostics use `nodesExplored`, `nodeLimit`, `budgetExhausted`, `candidateCount`, and `method`; all consumers use those producer names. `validateReliefPlan(world,plan)` independently checks every constraint and objective; returns `{valid:boolean,errors:string[]}`. It must reject fabricated IDs, duplicate aircraft/crew/requests, illegal slots, wrong arrivals, payload/cold-chain/qualification/duty/deadline breaches, expired data, blocked weather, closed/capacity-exceeded airports and objective mismatch. Root will pass previous assignments when validating changed count if supported.

`trainDemandModel({seed=26250,samples=120}={})` returns a serializable model/evaluation artifact with an independent held-out split, seed, feature definition, training count, MAE and baseline MAE. `forecastDemand(model,day)` returns bounded finite demand only; forecast is displayed, does not invent requests or alter hard constraints. No external training data or real-world accuracy claim.

`loadReliefAIConfig(env)` / `createReliefAnnotator(config,{fetchImpl}={})`. Config: `RELIEF_AI_MODE=deterministic|ollama` default deterministic; `OLLAMA_URL` loopback-only canonical HTTP origin; model map only five agent IDs; bounded timeout/context/output. `annotate({runId,revision,agentReports})` returns `{mode,modelsUsed,highlights:[{agentId,findingIds,status,model?}],generatedAt}`. Local LLMs may select known finding IDs only; strict schema plus post-validation deny invented IDs/text. All findings remain visible independently of selected highlights. No tools, arbitrary chat, execution privileges or remote endpoint. Failures/timeouts become explicitly labelled deterministic fallback; no fake model success. At most one model request at a time. Timeout and response byte limits are mandatory. Configured model names/version/digest are recorded in runbook when tested.

## API and persistence

- Admin GET `/v1/simulation`: idle or current snapshot.
- Admin POST `/v1/simulation/start` strict `{scenario:'civilian-relief',commandId:UUID,replaceRunId?:UUID}`. If a run exists, its exact runId is required for deliberate replacement. Exact command replay returns original saved response; changed content same commandId conflicts. Max1000 retained commands; saturation fails closed.
- Admin POST `/v1/simulation/step` strict `{commandId:UUID,runId:UUID,expectedRevision:integer,phase:enum}`. Phase must be the next fixed phase; wrong run/revision/order is409 with no state/event changes. Phases: weather-change, maintenance-change, airport-closure, new-request, validity-expiry. Every accepted phase increments revision once and automatically replans.
- Viewer GET `/monitor/api/simulation`: same current snapshot; no browser write buttons or admin token. No arbitrary query fields. Existing cookie/auth/no-store/CSRF contracts remain.
- Snapshot `{status:'idle'}` or `{status:'ready',world,plan,validation,demand,annotations,nextPhase,history,generatedAt}`. Entire content is fictional. `annotations` can be pending/disabled/degraded and always includes runId/revision. Late annotation cannot attach to a different revision.

Store simulation state and command receipts in the gateway's SQLite database, atomically with normalized fictional event history/outbox writes. Nested EventStore transactions use synchronous savepoints; no awaiting/network inside transactions. Injected state-write failure must roll back every ingested event/outbox and command. Root owns schema additions. Use the existing per-type configured source identity when mirroring fixture events; skip mirroring is not allowed if source permission is missing. World-only metadata such as cold storage, priority and slots is labelled scenario metadata, not added silently to gateway schemas.

Service `ReliefSimulationService({store,sources,now,annotator})` has `snapshot()`, `start(command)`, `step(command)`, `close()`. Annotation runs in a coalesced bounded background loop after committed state changes. It stores only matching current revision results, handles failures with static codes and shuts down before EventStore closes. Durable stored world+plan survives restart; ongoing model annotation resumes when configured. History is capped6 revisions per run; only current run state is kept, command receipts retained to1000. Commands contain no secrets.

## Tasks and ownership

1. Root writes world/perturbation builder, integration/service/API/store changes, CLI and tests. Uses Node/Express/Zod already pinned; no new JS dependency.
2. Planner subagent owns `src/relief-planner.js`, `test/relief-planner.test.js`; implements reports, finite optimizer and independent verifier. No shared edits.
3. Models subagent owns `src/relief-models.js`, `src/relief-ai.js`, `test/relief-models.test.js`, `test/relief-ai.test.js`, `scripts/train-relief-models.js`. Own docs may be `docs/relief-models.md`. Verify libraries with Context7. No shared edits.
4. UI subagent owns `web/relief.js`, `web/relief.css`, plus minimal mount changes to web/index.html and app.js. Existing auth-loss clearData must clear simulation reports/annotations too; no new token storage. Show fictional banner, revision/tick, assignment table, unmet requests, objective/status/budget, five specialist reports, checker, synthetic forecast, annotation provider/model state, next phase, prior revisions. Fetch in existing nonoverlap polling flow; discard stale/aborted responses; no standalone poll race. Responsive keyboard-safe text DOM only.
5. Root writes detailed guide, installs/tests optional local Ollama models on loopback, generates contracts, documents limitations, evaluates real HTTP→Kafka path and browser scenarios. Independent reviews then final review.

## Required validation

Known small optimum, objective hierarchy, budget label, deterministic repeat, all hard constraints, deliberate invalid plans, missing/expired data, no feasible assignments, perturbations/replanning. Command replay/conflict/stale revision atomicity and restart persistence. Model schema/unknown finding rejection, timeout/size/busy fallback, local endpoint restriction and separate synthetic train/test split. Real-model smoke if installed; explicit fallback otherwise. Existing96 tests remain unweakened. Full gateway→Kafka→reader fixture smoke and authenticated browser update/inspection/clearing tests. Detailed guide describes runnable code, not future stubs or combat adaptation.
