# AERONIQ - Decision Intelligence

Next.js dashboard with 11 main routes for ingestion, evidence, validity, forecasts, planning, stress testing, explanations, approvals, audit, and benchmarks.

## Run locally

Requires Node.js 22.18 or newer.

```sh
npm install
npm run dev
```

Open http://localhost:3000. In Windows PowerShell, use `npm.cmd` if script execution is restricted.

## Demo workspace

Demo mode is enabled by default and requires no backend. The workspace selector switches between demo data and the API configured by `NEXT_PUBLIC_API_URL` in `.env.local`. Live API errors remain visible; they do not fall back to synthetic results.

Demo state is saved in this browser's local storage. Use Workspace settings > Reset demo data to restore the examples.

- Inspect all four issue classes and validity statuses, linked evidence, provenance, and audit entries.
- Re-verify DEC-802 to refresh stale inputs. Invalidated and uncertain decisions remain blocked.
- Switch the forecast scenario to display high uncertainty and reduced coverage.
- Planning starts with SCH-842; compare SCH-841 and SCH-842 for additions, removals, and moved assignments. Run optimisation to create another schedule and approval request.
- Launch stress runs with a scenario, integer seed, and severity. Runs progress from running to completed with deterministic illustrative metrics.
- Submit an agent question to see a simulated trace and evidence-linked explanation.
- Approve a verified schedule or reject an invalid/uncertain result with a reviewer and rationale. The action appears in Audit.

All demo metrics, explanations, and verification outcomes are illustrative, not backend measurements. Scheduling uses the local heuristic. Changes never reach the backend in demo mode.

## Validation

```sh
npm run build
npm run typecheck
npm test
```

Browser tests use Python Playwright and installed Microsoft Edge. Start the production app on port 3100, then run from the repository root:

```sh
python frontend/tests/demo_workflows.py
python frontend/tests/ui_smoke.py
python frontend/tests/failure_states.py
```

The demo workflow checks run without backend interception. The other suites intercept API responses to check live success and failure states.
