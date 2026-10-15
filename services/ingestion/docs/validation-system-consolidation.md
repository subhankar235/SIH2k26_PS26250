# System consolidation validation

Validated on 2026-10-15 in the isolated `feature/logistics-ingestion` worktree, starting from `7cbb678`. The original `SIH2k26_PS26250` worktree was left unchanged.

## Change

Relocated 23 source files into named modules and seven browser assets into `dashboard/`, preserving exports, API routes, schemas, event/planning atomicity, database locations and fixed bounds. Added root npm delegation, a module guide, a consolidated feature blueprint and an isolated offline system journey. No runtime dependency or database schema changed.

## Observed checks

| Check | Observed result |
| --- | --- |
| `npm run verify` from root | Passed: syntax of 77 JavaScript files; generated contracts match; all 201 tests pass, none skipped |
| Existing regression assertions | Original 198 tests retained; their changes are import paths only |
| New database-root assertions | Gateway and reader still resolve separate databases under the service's `var/` |
| `npm run demo:offline` | Passed isolated real HTTP/SQLite journey; scores `[9,7,6,0,9]`, five revisions, source duplicate, batch, injected-clock expiry, viewer restrictions and persisted restart |
| `npm run test:pipeline -- --browser` | Passed using the actual development Kafka broker; five revisions, 84 events delivered/read, duplicate source input, actual timer expiry, reader restart and application restart |
| Executed negotiation in real pipeline | Five rounds completed, 271 directed messages in initial report; proposals/objections/bids/counters/acceptances/commits and grounded references checked |
| Browser attached to real pipeline | Passed source-driven viewer polling, automatic expiry, four viewports and logout |
| `npm run test:dashboard` | Passed negotiation fixture: grounded transcript, proposal correlation, budgets/history, focus/scroll, safe DOM, four viewports, auth clearing and no mutation requests |
| Relief and dynamic browser fixtures | Both passed after asset relocation |
| `docker build --tag logistics-consolidation:local .` | Passed lifecycle-disabled locked installation and explicit KafkaJS compatibility setup; relocated dashboard copied into image |
| Container runtime | Passed as unprivileged `node`, networking disabled: readiness, actual dashboard HTML/JS, initial checked/negotiated proposal and `/app/var/read-model.sqlite` path |
| Relative Markdown links | All root design/current service documentation links resolve |
| Git whitespace check | Passed after staging |

The offline journey uses new temporary credentials and its own temporary SQLite database and removes only that directory on completion. It explicitly checks that Kafka-disabled events stay queued and are never reported published. The real pipeline uses unique test database names and a unique consumer group, preserving the application's active databases.

## Review and limits

A fresh builder review checked the design/feature ledger, then reviewed the staged source relocation, root/CI commands and integrated test. No blocking correctness/security findings were reported; a shorthand source path in the engine guide was corrected.

The tests establish the current bounded fictional logistics behavior. They do not establish military problem-statement completion, production throughput, multi-replica availability, real-world forecast accuracy or operational suitability. Public weather and optional Ollama/Gemma/Qwen calls were not rerun for this consolidation; their code only moved. Hosted CI was updated but was not executed from this session.

Antigravity CLI was detected. An attempted read-only documentation lookup produced no usable result: headless file-read permission was denied. No permission bypass was enabled; implementation and reasoning were performed by Codex, with a separate review agent.

See the [module map](SYSTEM_MODULES.md) and [feature blueprint](../../../docs/PROJECT_BLUEPRINT.md).
