# Autonomous civilian negotiating agents

The relief engine now runs autonomous deterministic policy agents before each optimization. This is executed negotiation: peer messages, objections and bid intersections determine a feasible incumbent. The existing coordination summary remains separate from this conversation. Gemma/Qwen remain optional evidence selectors and do not negotiate, choose assignments or relax constraints.

## Running and configuring it

From `services/ingestion`, restart the API with `npm start`, then run `npm run relief:dynamic`. Open `/monitor/` with the existing separate viewer token and inspect **Autonomous civilian negotiation**, especially its peer message ledger. The demo changes all five ordinary source domains and the engine negotiates each accepted revision. `npm run relief:dynamic -- --weather` also exercises the explicit public weather provider.

Negotiation defaults on for newly started runs. Existing saved snapshots acquire the new report on their next actual revision; merely reading or restarting does not fabricate a conversation for an old revision. To start a run with explicit settings, the admin start command accepts the existing fields plus:

```json
{
  "scenario": "civilian-relief",
  "inputMode": "gateway",
  "commandId": "supply a fresh UUID",
  "negotiation": { "enabled": true, "maxRounds": 4, "maxMessages": 512 }
}
```

Supply the current `replaceRunId` when replacing an existing run. Omitted settings use enabled=true,4rounds and512messages. Fields are strict; enabled must be boolean, rounds1..8 and messages32..512. These settings persist across scripted, gateway, expiry and weather revisions. Setting enabled=false explicitly preserves ordinary optimization with a disabled negotiation report; it does not disable hard constraints or verification.

## The five agents

Each specialist owns an inbox, local reservations, policy, accepted/rejected proposal IDs and bid count. It reads a detached immutable-by-convention world snapshot and receives actual routed messages. Agents execute in one Node process, not separate distributed workers or LLM sessions.

| Agent | Independent veto checks | Preference for admissible alternatives |
| --- | --- | --- |
| Fleet | Availability, expiry, origin, payload, cold storage, aircraft reservation | Retain earlier assignment where possible, preserve cold-capable aircraft for suitable cargo, reduce spare payload |
| Crew | Availability, expiry, qualification, duty coverage, crew reservation | Retain earlier assignment, prefer shorter duty windows, earlier arrival |
| Weather | Endpoint evidence, expiry, numerical wind and visibility | Retain earlier assignment and earlier arrival |
| Airport | Endpoint status/expiry and shared arrival/departure capacity | Retain earlier assignment and earlier departure |
| Cargo | Request expiry, directed route, deadline, duplicate request | Higher-priority requests first; retain prior assignment and earlier arrival |

These preferences rank proposals. They do not alter the global objective, request priorities, resource limits or mandatory vetoes. The world remains the existing bounded fictional one-wave model: at most3aircraft,3crews,3airports,2routes and5ordinary cargo requests. No combat functions, real dispatch, weather certification or unconstrained tool execution is introduced.

## The negotiation loop

1. Cargo orders requests by decreasing scenario priority and stable ID. It sends a call for proposals to the four other peers, then proposes a canonical resource/slot tuple.
2. Every specialist independently evaluates that tuple against its own constraints and current reservations. Each acceptance or objection is delivered to the other four peers and the supervisor. This creates all20directed peer links, not only specialist-to-supervisor reports.
3. On objections, each agent independently advertises its locally acceptable candidate IDs. Those bid messages are delivered to peers and supervisor. An objecting agent can propose an untried alternative supported by every advertised peer bid.
4. Cargo consumes received counterproposals and its own applicable policy state to choose the next proposal. Local preferences can differ, but no alternative bypasses the next complete vote.
5. Only five distinct acceptances delivered to the supervisor permit commitment. The supervisor broadcasts that commitment to all five actors; the actual commit deliveries update their reservation state. Subsequent requests cannot silently reuse a committed aircraft, crew or occupied capacity.
6. No joint alternative, a round limit or message exhaustion leaves an explicit blocked/deferred/budget-exhausted request. The engine returns its already verified feasible commitments rather than claiming consensus from incomplete votes.
7. The deterministic optimizer uses that incumbent as a checked warm start, then searches under the unchanged objective and tie rules. An independent checker verifies the final proposal. The outcome states whether the negotiated seed was retained or the optimizer refined it.

Messages include run/revision-specific IDs, request/proposal/candidate IDs, canonical assignment tuples where relevant, current finding IDs, assignment-specific rule codes and fixed policy summaries. A condition label is not a new numerical weather constraint. Source priority and cold-storage metadata are not invented during bargaining.

## Bounded execution and failure behavior

There are at most135raw resource/slot candidates. Rounds are bounded per request; message budget covers actual directed deliveries. An entire delivery group must fit before any of that group reaches mailboxes. A partial voting set cannot commit. Small budgets can intentionally prevent any consensus; for example32messages cannot complete the default first full commitment. Ordinary exact optimization still produces a verified proposal from whatever feasible seed exists.

Statuses distinguish agreed, partial, no_agreement, budget_exhausted, failed and disabled. Partial agreement can be a healthy result: the default fixture has four requests but only two available crews. `roundsCompleted` totals attempts across requests, so it can exceed maxRounds, which applies separately to each request. The message count never exceeds the configured global budget.

Agent faults, asynchronous policy returns or invalid traces produce explicit failed status/NEGOTIATION_FAILED and an unseeded deterministic optimization fallback. Raw exception messages are not exposed. Policies receive detached world/prior/settings copies, so a faulty policy cannot modify persisted facts, objectives or configuration. No agent performs network calls inside the database transaction.

Negotiation remains inside the existing synchronous transaction containing input facts, world mapping, optimizer, checker and outbox mirrors. State/outbox failures roll the whole change back. Exact command replay returns the saved original conversation without executing a second negotiation. Every new revision starts fresh agent mailboxes/reservations, with prior assignments used only as bounded preference context. Source/admin/viewer authentication and TTL protection remain intact.

## Audit and optimizer authority

The transcript is audited before its incumbent enters optimization. Deterministic replay checks all metadata, policy choices, delivery groups, bid/counter causality and actor summaries against the exact world and prior plan. Separate checks verify canonical candidate references, each local supervisor vote, five-way acceptance, complete commitment delivery and feasibility of the resulting seed. Replay detects tampering; the independent constraint checker protects against invalid negotiation outcomes. Neither is a proof that distributed negotiation alone finds a global optimum.

Reports retain at most five previous assignments, making policy replay context self-contained. Runtime audit additionally binds them to the service's actual previous plan. `getReliefNegotiationContext`, `validateReliefAssignmentSeed`, `runReliefNegotiation`, `validateReliefNegotiationReport` and `finishReliefNegotiation` are internal JavaScript interfaces, not callable tools exposed to agents through HTTP.

A full exact search preserves the same optimum and canonical tie result as before. A checked seed is especially useful when the search budget is small: a one-node run can retain a negotiated feasible incumbent rather than returning the empty incumbent. No search-performance or operational-quality improvement is claimed beyond the measured bounded tests.

## Persistence and dashboard

The current report is stored under snapshot.negotiation in relief_state in the same SQLite commit as the proposal. Admin command receipts also retain their original response including the report. Current negotiation survives service restart. Gateway-triggered older full transcripts are replaced by the latest snapshot; the existing revision history retains summaries, not an unlimited conversation archive. Canonical source/outbox history is unchanged. Negotiation messages are in-process communications and snapshot audit data, not a new Kafka topic or distributed actor transport.

The viewer shows status, limits, rounds, agent activity, request results, seed assignments, seed/final served priority and the typed ledger. It correlates every vote/commit with the matching proposal request/round/candidate; merely knowing an ID is insufficient. Contradictory references and unknown evidence are omitted with a warning. It labels expiry-pending conversations historical and suppresses reports for a different run/revision. Viewer polling is observational and cannot execute bargaining or dispatch anything.

## Validation and code map

- src/relief-planner.js: bounded candidate context, independent seed validation and checked warm starts.
- src/relief-negotiation.js: local specialist policies, inboxes, routing, budgets, bid intersection, audit and final outcome.
- src/relief-service.js: persisted settings, automatic per-revision execution, isolation/fallback and atomic state.
- web/relief.js: grounded read-only negotiation inspection.
- test/relief-seed.test.js, relief-negotiation.test.js and relief-negotiation-service.test.js: meaningful safety, optimality, budget, mutation and rollback checks.

Run `npm test`, `npm run contracts:check`, `npm run check`, `python scripts/negotiation-ui-fixture.py`, and `npm run relief:test:dynamic -- --browser`. The latter verifies real HTTP updates, Kafka/durable reader, automatic TTL expiry, service/consumer restart with persisted negotiation and actual browser counterproposals. Fixtures cover malicious strings, known-but-contradictory references, stale/historical reports, all statuses, keyboard/scroll preservation and four viewports. Validation evidence: [validation-negotiation.md](validation-negotiation.md).
