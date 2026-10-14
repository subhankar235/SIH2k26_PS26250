# Civilian relief viewer implementation

Implemented task 4 in `services/ingestion/web`: new `relief.js` and `relief.css`, plus minimal mounting and polling changes in `index.html` and `app.js`.

The separate read-only section follows the existing monitor's teal/neutral tokens, typography, tables and disclosure patterns. It labels the fixed fictional civilian scenario, logical ticks/slots, proposed assignments and educational limits explicitly. Fact filters do not alter the scenario. It displays current run/revision/phase, assignment and unmet-request tables, exact versus budget-limited search status, lexicographic objective and explored/limit counters, independent validation and errors, synthetic demand evaluation, all five specialist reports and finding IDs, local-model/deterministic/fallback state, fictional world metadata and revision history.

The simulation GET runs inside the existing nonoverlap refresh using the same AbortController and generation. Responses are checked after JSON awaits and before DOM rendering. A missing endpoint or transient simulation error clears only relief content and leaves reported facts available. Annotation run/revision mismatches are ignored. Selected evidence IDs are intersected with the corresponding specialist's actual finding IDs. Every displayed value uses text DOM; no data is rendered as HTML, no write controls or administrator/source credentials were added, and no token or simulation snapshot is stored in browser storage.

`reliefClear()` clears all dynamic relief DOM and status text on session loss, logout (including failed logout), and fact-filter reset. No module-level simulation data is retained. Disclosure open state and keyboard focus survive normal polling.

## Verification

- RED: the browser fixture failed because the Civilian relief simulation heading did not exist before implementation.
- GREEN: `python .superpowers/sdd/civilian-relief-engine-plan/ui-browser-check.py` passes in headless Chromium against the actual assembled static viewer with isolated API fixtures.
- Fixtures cover ready/idle/404, exact/budget labels, assignments/no feasible assignments, unmet reason codes, checker failures, forecast/history, safe malicious-looking finding text, local/deterministic/fallback models, pending and mismatched annotations, keyboard disclosure persistence, widths 320/768/1024/1440 without document overflow, simulation 401, successful/failed logout clearing, overlapping-refresh suppression, and delayed response discard after sign-out.
- `node --test test/monitoring.test.js` passes: 6 tests, no failures or skips, preserving existing monitor authentication and session behavior.
- `npm run check` passes; most recent run syntax-checked 56 JavaScript files, including concurrently added backend files.
- Desktop/mobile PNGs were visually inspected. They are generated local evidence in this report directory, not committed artifacts.

Self-review checked correctness, auth clearing, safe rendering, module boundaries, accessibility and bounded rendering. No backend, store, configuration, package or shared `render.js` changes were made by the UI task. Live simulation/backend integration and full suite are left to the root's final integration pass because backend work is concurrent; the fixture checks do not claim a real-model invocation or live backend smoke.

## Reproduce

Run the browser fixture from repository root. It uses the already-installed Python Playwright, serves `services/ingestion/web` on an ephemeral loopback port, needs no tokens and shuts down the server afterward. Run the monitor tests and `npm run check` from `services/ingestion`.
