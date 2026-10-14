# Dynamic civilian system validation

Validated on2026-10-15 in the isolated feature/logistics-ingestion worktree. Baseline before this increment: ed8ecc0. Existing original workspace remains unchanged.

## Behavior and invariants

- Authenticated bound source updates drive atomic world mapping, solver, independent check and mirrored outbox publication. One effective batch means one revision; exact event replay does not replan.
- Stale/expired/unbound/wrong-run/nonauthoritative events do not alter the plan. Invalid mappings, DB failure and outbox saturation roll back input history and all derived state.
- TTL expiration and future aircraft maintenance deadlines invalidate resource evidence; failed expiry commits make prior proposals historical. Mirrors inherit effective TTL and retain maintenance/temperature evidence; expired inputs are not refreshed by replanning. Absolute duty/deadline slots remain anchored at createdAt.
- Public weather is explicit admin-only single flight, fixed HTTPS presets, bounded timeout/body, UTC/units/data/freshness validation, distinct visibility time, abort/drain. Degraded responses contain no fabricated input. Success/degraded/finalization-error receipts replay without refetch; superseded run results cannot apply. Removed source authority refuses weather before network execution.
- Configurations have strict bounded schemas and resolving references; no arbitrary real resource IDs, weapons, objectives or provider URLs. Coordination references current deterministic findings; optional local LLMs still cannot generate assignments.

## Real runtime evidence

`node --env-file-if-exists=.env scripts/dynamic-smoke.js --live-weather --browser` verified HTTP/Kafka/reader plus a real public Delhi estimate. Six revisions and101events were stored, published and consumed, with exact source/admin replay and consumer restart. The first browser attempt used a wrong expected heading and failed before sending a source update; the selector was corrected to the actual rendered heading.

`node --env-file-if-exists=.env scripts/dynamic-smoke.js --browser` then completed five source/expiry/restoration revisions and84events, verified all published and durably consumed across reader restart, and passed the actual browser source update, polling, automatic expiry, four viewports(320,768,1024,1440) and logout clearing. The smoke uses unique SQLite files and consumer groups and closes both runtimes. Local evidence: ignored var/dynamic-smoke.log and var/dynamic-browser-live.png.

The live weather response preserved Open-Meteo weatherTime2026-10-14T23:30Z, visibilityTime23:00Z and fetchedAt23:33:00Z (2026-10-15 local date). These are weather model estimates for city-centre coordinates, not aviation observations. Network success is evidence of integration, not real-world scheduling accuracy.

Dynamic and existing Playwright fixtures both passed. Desktop/mobile screenshots were inspected; unsafe strings and unknown evidence IDs remain inert, no viewport overflow, and focus/disclosure/scroll state survives polling. See validation-dynamic-ui.md.

Independent task reviews found and verified fixes for qualification grammar, empty-world configuration, WMO97, receipt-time maintenance checks, mirrored TTL evidence, slot anchoring and weather finalization replay. Source-backed docs were retrieved through Context7 for Zod, Open-Meteo and Express5 async error propagation. agy gemini-3.8-flash-high performed bounded read-only smoke-harness inspection; root implemented and reasoned about integration.

No military planning, autonomous negotiating network, real fleet dispatch or production scalability claim is made. The bounded revision/resource/command limits are documented in DYNAMIC_CIVILIAN_GUIDE.md.
Final verification: 178unit tests passed with0failures/0skips;72JavaScript files passed syntax checks; generated OpenAPI/event schemas match source. Broad independent review approved after regression fixes for full-outbox restart recovery and configurable airport-ID compatibility. The configured main demo also passed nine revisions through all five source domains and real public weather with independent verification. No required review finding remains.
