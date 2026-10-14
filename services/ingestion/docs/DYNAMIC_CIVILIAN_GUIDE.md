# Dynamic civilian relief system

This increment connects the existing authenticated gateway to the bounded fictional relief planner. It adds configurable fixtures, deterministic specialist coordination, input expiry and manually refreshed public weather. It is a civilian educational demonstrator. The resource model remains three aircraft, three crews, three airports, two routes and five medical/food/water/equipment requests. It does not implement the original problem statement's military combat functions or real aviation dispatch.

## Run it

From `services/ingestion`, use the existing credential file and broker setup described in the service README. Start the current code with `npm start`, then run:

```powershell
npm run relief:dynamic
# Also request public model-estimated weather for a fictional airport:
npm run relief:dynamic -- --weather
# Load an editable strict fixture:
npm run relief:dynamic -- --configuration docs/configurable-relief-example.json
```

The dynamic demo replaces the current fictional run using its exact run ID. It posts authenticated weather, aircraft maintenance, airport closure/restoration, cargo and crew updates. Each accepted effective batch produces a new independently verified proposal. Open `http://127.0.0.1:3100/monitor/` using the separate viewer token to inspect it. The viewer polls every five seconds while visible. API expiry checks run every second. These are proposals; no delivery is executed.

`npm run relief:demo -- --fast` still runs the original five scripted perturbations. Scripted runs ignore source-driven updates; gateway runs do not permit scripted step commands. To switch modes, start a new run with the current `replaceRunId`.

## Start a configurable run

Admin POST `/v1/simulation/start` accepts:

```json
{
  "scenario": "civilian-relief",
  "inputMode": "gateway",
  "commandId": "a fresh UUID",
  "replaceRunId": "current run UUID, only if one exists",
  "configuration": { "aircraft": [], "crews": [], "airports": [], "weather": [], "routes": [], "requests": [] }
}
```

The abbreviated empty configuration above shows the field names; a wholly empty scenario is invalid. Use the complete [example](configurable-relief-example.json), edit bounded fields, and send the actual generated UUIDs. Configuration is optional; omitting it selects the original civilian relief world. Custom configuration requires gateway mode. Demand history is optional display metadata; the trained synthetic demand model and its held-out evaluation remain separate and do not create requests.

Every object is strict. Unknown fields are rejected rather than ignored. Server-owned identity, revision, creation time, policy and search limits cannot be overridden. IDs begin `SIM-`, use letters/digits/underscore/hyphen, and total at most20 characters. This keeps the output UUID namespace plus ID within the gateway's64-character identifier limit. IDs for aircraft/crew/airports/requests are globally unique. Airport references, weather coverage and each request's directed route must resolve. A usable airport participates in a configured route. Duty intervals are increasing, closed airports have zero capacity, and crew qualifications begin with a lowercase letter and contain only lowercase letters/hyphens.

The fixed toy horizon has departure slots0,1,2,30minutes each, route duration1slot, numerical weather thresholds and request priorities1..5. These are educational rules, not aviation operating minima. Each aircraft and crew is used at most once in the wave. The optimizer maximizes served priority, then minimizes changes to surviving prior assignments, then minimizes arrival slots. A separate checker verifies IDs, resource use, hard constraints and objective arithmetic. Search budget exhaustion produces a feasible_budget result rather than a false optimality claim.

## Source-driven ingestion

Read `/v1/simulation` using the admin credential. The `inputs` object gives an exact namespace and designated authority for each canonical type. Authorities are chosen from the first configured source permitted for that type at run creation and persisted. Other sources retain their independent history but cannot override this run. If source configuration changes, create a new run to choose fresh authorities; do not assume configuration ordering silently rebinds the existing run.

For example, send ordinary weather to the existing source endpoint with the designated weather source credential:

```json
{
  "schemaVersion": 1,
  "eventId": "a fresh UUID",
  "sourceId": "the designated weather source ID",
  "type": "weather.observation",
  "entityId": "input-<current run UUID>-SIM-CLINIC",
  "sequence": 1,
  "observedAt": "actual current ISO UTC timestamp",
  "validUntil": "a later ISO UTC timestamp",
  "data": { "temperatureC": 24, "windSpeedMps": 25, "visibilityM": 1500, "condition": "storm" }
}
```

Use concrete UUID/timestamp values, not the explanatory placeholders. POST `/v1/events/batch` accepts up to100 source-authorized events under `{events:[...]}`; all must be permitted by the same credential. Receipt shapes remain unchanged. The simulation snapshot exposes the resulting revision and current bindings. A stale, expired, duplicate, wrong-run, unknown-entity or nonauthoritative fact does not replan. Unbound ordinary facts are still ingested normally. The `relief-<UUID>-` output namespace is distinct and cannot feed back into the input path.

The entire validated batch, world mapping, optimizer result, independent check and mirrored outbox records commit in one SQLite transaction. Invalid mapping, conflicting stream, state write failure or outbox saturation rolls the whole batch back. Clients may safely retry exact event IDs with identical content. Reuse with altered content conflicts. Kafka remains asynchronous and at least once; receipt success means durable persistence, not broker delivery. The durable consumer deduplicates and checkpoints before acknowledging.

### Mapping rules

| Input type | World effect | Additional bounded requirements |
| --- | --- | --- |
| aircraft.status | status, location, capacity | Airport reference uses this input namespace. Cold storage stays scenario-owned. Maintenance due dates use receipt time; a future due date limits effective validity. |
| crew.availability | status, qualifications, duty slots | Times align exactly to30-minute offsets from run createdAt, within0..4, increasing. At most8 unique lowercase qualifications. |
| weather.observation | temperature, wind, visibility, condition | Canonical numerical/enumeration bounds. Feasibility uses numerical wind/visibility; the condition label is display metadata. |
| airport.capacity | status, arrival/departure capacity | Hourly capacities are even integers0..6, divided by2 into per-slot capacities. Closed means zero. |
| cargo.request | category, mass, endpoints, deadline, cold-chain need | Existing request only; endpoints and route resolve; delivery aligns to slots1..4 from createdAt. Scenario priority stays unchanged. |

The gateway does not introduce arbitrary new resources or requests into a run. Customize those at start. Absolute duty and deadline mirrors remain anchored to createdAt rather than sliding forward with each update. Source temperature and maintenance timestamps are retained in derived mirrors.

### Expiry and bounded revisions

Applied bindings persist their event IDs, source/type/entity references, observedAt, effective validUntil and expiry state. Wall-clock TTL differs from the scripted world's logical tick. At expiry, the service invalidates that resource and solves/checks another proposal. Refreshing it with a newer valid canonical event restores its current evidence. Prior input history remains available separately.

Mirrors inherit each bound input's effective validity window. Expired bindings are omitted on later replans; their last mirror expires naturally in the gateway and reader. Replanning cannot turn an expired available aircraft or weather reading into a newly fresh fact. A run with all bound resources expired can commit a verified empty plan with zero new mirrors.

If backlog or storage failure prevents expiry committing, snapshot reads derive `planUsable:false` and `inputFreshness.replanPending:true` from current time. The viewer marks the previous assignments/checker/coordination as historical. Once an independently checked expiry revision commits, `planUsable:true` returns, even though expired binding evidence remains in the audit table. That plan excludes the expired resources.

To preserve the existing bounded demonstration and retained history, a run accepts new updates at current revisions0..18, possibly creating revision19. Bound input at19 is rejected atomically with `SIMULATION_REVISION_CAPACITY`; ordinary unbound ingestion continues. The final reserved expiry revision20 invalidates any remaining bound resource validity (`expiryReason:revision-capacity` where applicable). Start a new run to continue. This is an explicit demo capacity boundary, not an unlimited operational scheduler. Retained admin command receipts are capped at1000 across runs and are not automatically pruned.

## Structured specialist coordination

The snapshot contains five deterministic specialist evidence messages to a supervisor and a grounded resolution. Each message includes from/to/kind, entity IDs, current finding IDs and a summary. The supervisor summarizes the independently checked assignment result. The dashboard filters unknown finding IDs defensively and labels historical coordination if expiry is pending.

This is an inspectable evidence exchange, not an autonomous negotiating-agent network. It does not change the objective or hard constraints. Existing optional local Ollama models still select allowlisted finding IDs for annotations; deterministic rules and the optimizer remain authoritative. Forecast evaluation remains synthetic and cannot establish real operational accuracy.

## Live public weather

Admin POST `/v1/simulation/weather` accepts `{commandId,runId,expectedRevision,airportId,location}`. The run must be gateway mode, the airport already exists, revision is0..18, and location is exactly `delhi`, `mumbai` or `chennai`. Example airports are fictional; city-centre coordinates are mapped explicitly for the demonstration. The server does not fetch weather automatically when a viewer polls.

The provider uses fixed HTTPS Open-Meteo forecast endpoints and requests current temperature/wind/weather code plus hourly visibility in explicit UTC units. These are weather model estimates, not airport sensors or aviation reports. The nearest hour may be a future forecast sample, and its distinct timestamp is shown. Current estimates older than30minutes, more than60seconds in the future, missing nearest visibility, invalid units, malformed timestamps, unknown codes or out-of-range values fail explicitly. No missing field is replaced with clear weather or another guessed value. See the [provider specification and primary sources](weather-provider.md).

Network requests run outside SQLite transactions, with a10-second timeout,64KiB response bound, redirect rejection and single-flight limit. Only fixed aliases are accepted, so credentials or attacker-supplied URLs cannot be sent upstream. On shutdown the active provider aborts and drains. After fetch, the original run/revision is checked again; late results cannot update another run. A stale provider reading cannot overwrite a newer input observation.

Successful refresh produces a canonical weather event through the same atomic ingestion/replanning path, including stored sequence advancement. Provider failure persists `weatherFeed.status:degraded`, errorCode and timestamp without inventing input or incrementing the world revision. The endpoint returns200 for this recorded degraded result; callers must inspect weatherFeed.status. Successful/degraded command responses replay exactly without fetching again. Finalization failures after fetching retain durable structured error receipts and replay the same error; use a new UUID to retry after recovery. Command capacity failures before a network request cannot retain another receipt. Different concurrent weather commands fail busy; identical concurrent commands share one request. A restart marks an interrupted pending request `WEATHER_INTERRUPTED`.

The viewer displays provider provenance, separate weather/visibility/fetch times, error state, and an earlier-revision warning if a subsequent update changed the plan. A prior provider result is never silently represented as current-run data after run replacement. Viewer credentials and cookies cannot execute weather/start/step commands.

## Verification

```powershell
npm test
npm run contracts:check
npm run check
npm run relief:test:dynamic -- --live-weather --browser
npm run relief:test:dynamic-ui
```

The dynamic smoke uses isolated SQLite paths, consumer group and loopback port31875. It verifies source replay, batch revision coalescing, automatic TTL expiry, restoration, independent checking, real Kafka publishing, durable reader persistence and reader restart. The default run expects five revisions/84events; optional live weather adds one revision/17events when usable. The browser option verifies actual authenticated source updates reaching viewer polling, timer expiry, four viewports and logout clearing. Fixtures separately exercise malicious strings, unknown finding IDs, provider failure/stale states, keyboard focus and overflow.

The public provider can legitimately be unavailable or reject stale/invalid estimates; the test requiring live success reports that failure explicitly. The offline unit suite covers those errors deterministically. Local `.env`, SQLite files, model artifacts and screenshots stay ignored. Validation results are recorded in [validation-dynamic-system.md](validation-dynamic-system.md).
