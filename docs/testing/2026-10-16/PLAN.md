# System verification plan — 16 October 2026

## Objective

Execute at least 1,000 individually identified scenarios against the current implementation. Preserve each scenario's inputs, expectation, observed result, duration, execution layer, and failure classification. A parameterized case is one distinct input scenario, not one assertion or HTTP request.

## Execution slices

1. Inventory the running API and frontend; save OpenAPI and source fingerprints. Read-only live requests cover routing, response contracts, missing resources and wrong methods.
2. Exercise the actual Python app through ASGI with isolated module registries and an in-memory storage double. Cover request validation, solve/verify consistency, permissions, approvals, disruptions, duplicates and fault injection. These are not live network or real PostgreSQL tests.
3. Run solver boundary matrices against an independent arithmetic oracle, invalid-assignment matrices against the verifier, telemetry state transitions, consensus checks, restart and persistence failures. Use generic fictional transport data.
4. Exercise the running frontend in a real headless browser. Isolate mutations with intercepted API responses, test desktop/mobile routes and failure states, and record whether UI claims agree with returned evidence. Run existing suites separately.
5. Publish a case ledger (JSON and CSV), machine-readable summary, API coverage, baseline command logs and a readable report with prioritized remedies and explicit limits.

## Acceptance criteria

- At least 1,000 completed scenarios; blocked cases do not satisfy this threshold.
- No modification to application source, active server plans, existing credentials, broker topics or live database fixtures by the new audit harness.
- No blanket pass based on HTTP 200: assert domain invariants and failure semantics.
- Failures remain failures; do not weaken expectations to turn the report green.
- Live, ASGI, direct-domain, browser-mocked and injected-fault results remain distinguishable.
- Source hashes identify the tested snapshot and detect changes during execution.

## Limits

Finite matrices do not cover every possible input. This is not a production load benchmark, aviation validation or statistical model accuracy study. Existing PostgreSQL tests may use the configured development database and are reported separately. Kafka delivery/replay requires separate isolated-broker evidence; mere startup or a listening socket is insufficient.
