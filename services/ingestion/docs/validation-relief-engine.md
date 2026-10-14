# Civilian engine validation record

Implementation increment `7f9c50b..fb94ca8` on the isolated `feature/logistics-ingestion` branch. Independent core, models, UI and final reviews approved after required fixes. The original project worktree was left unchanged. This is the fixed fictional noncombat scenario described in the detailed guide; no combat-engine instructions or operational deployment are included.

| Verification | Result |
| --- | --- |
| Node unit/HTTP suite | 133 passed, zero failed/skipped |
| JavaScript syntax | 60 files checked |
| Generated contracts | OpenAPI/event schemas/fixtures match generators |
| Six logical scenario revisions | Independently checked priority sequence9,7,7,0,10,0 |
| Real relief HTTP→outbox→Kafka→reader | All98fixtureevents delivered,17source projections, exact command retry idempotent |
| Two actual local language models | All five specialist selections validated;37.3s observed one smoke, not a performance guarantee |
| Live native browser | Real authenticated updates across6revisions, exact numeric diagnostics, grounded reports/forecast/checker,4viewports/logout |
| Retained browser fixtures | ID safety, exact/budget labels, focus/scroll on polling/revisions, auth clearing, provider/fallback labels, delayed-response isolation |
| Rebuilt Linux application image | uid1000; same live6revision browser smoke passed, graceful exit0 |

Regression fixes include full UUID fixture namespaces, consistent mirrored airport references, atomic refusal of poisoned/stale fixture streams, training-only OLS residual checks that detect held-out fitting, keyboard table focus/scroll preservation, actual producer diagnostic field names, and accurate documentation of randomized holdout rather than chronological evaluation. Failure-triggered rollback, backlog/command capacity, restart persistence and obsolete-annotation rejection are covered by retained tests.

Runtime used Node24.19.0, Kafka4.1.1, Docker29.4.3, Ollama0.40.4 and Chromium. Ollama ran on loopback with cloud features disabled, CPU/memory bounds and sequential inference. Installed model manifests:

- `gemma3:270m`: `e7d36fb2c3b3293cfe56d55889867a064b3a2b22e98335f2e6e8a387e081d6be`,291554930bytes.
- `qwen3:0.6b`: `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`,522653767bytes.

Seed26250 synthetic demand artifact uses96training/24randomly held-out samples. Held-out MAE7.1425 versus training-mean baseline76.2292 evaluates synthetic interpolation. It does not establish chronological forecasting accuracy or real relief-demand accuracy. The displayed extrapolation cannot create requests or change hard constraints.

Private credentials, SQLite files, downloaded weights, training/model-smoke artifacts and screenshots are excluded from git. Model manifests are public provenance metadata. No automated accessibility certification, distributed/HA deployment, live external data adapter or real flight execution is claimed. Review scratch reports remain local under the ignored plan directory; reproducible test scripts and the guide are tracked.
