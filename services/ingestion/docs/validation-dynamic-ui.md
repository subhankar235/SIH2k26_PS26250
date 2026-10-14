# Dynamic civilian relief viewer validation

The monitor extends the existing read-only relief view using its current typography, semantic colors, table regions and keyboard disclosures. Gateway authority and input TTL are inspectable before the proposed assignments. Coordination is explicitly deterministic, with a verified decision summary and a collapsible message ledger. Weather status exposes the latest administrator-requested refresh and allowlisted provenance; viewing or polling never requests provider weather.

`planUsable:false` or `inputFreshness.replanPending:true` changes assignments, search result and checker labels to historical evidence. Successful expiry can retain expired binding records while restoring a usable verified plan. Earlier-revision weather results remain visible with a timestamp/TTL warning; results from a different run are suppressed.

Run from the repository root:

```powershell
python services/ingestion/scripts/dynamic-ui-fixture.py
python services/ingestion/scripts/relief-ui-fixture.py
node --check services/ingestion/web/relief.js
```

Verified in headless Chromium on 2026-10-15:

- Gateway namespace, designated authorities, event/source provenance, observed/valid-until UTC timestamps and expired/current binding states.
- Forty input bindings and coordination messages, with grounded finding IDs restricted to the current specialist reports. The fixture rejects an intentionally inverted grounding filter; original source is restored after this mutation check.
- Ready, pending and degraded weather states, fixed error codes, allowlisted provider coordinates/times, earlier-revision warnings and different-run suppression. Extra provenance fields never render.
- Expired inputs with pending and nonpending replans, historical checker/search/assignment labels, and restored usable proposals.
- Untrusted HTML strings remain literal text, with no injected images, scripts, frames or links and no provider/admin mutation controls or requests.
- Keyboard disclosure activation; open disclosure, table focus and both scroll offsets survive refreshes, revision changes and timer polling. Removed optional tables move focus to the simulation heading.
- Empty bindings/messages, scripted inputs and legacy snapshots without optional fields.
- Simulation 401 clears all optional evidence and returns to the existing viewer login.
- No page errors or document overflow at 320, 768, 1024 and 1440 pixels. Desktop and mobile captures were visually inspected.

The original relief fixture also checks annotations, independent-checker errors, assignment/history states, nested table focus, unavailable/idle views, logout failures and delayed-response discard. Authentication remains owned by the existing monitor code.

Screenshots are regenerated locally under `.superpowers/sdd/civilian-dynamic-extensions-plan/`: `dynamic-ui-1440.png`, `dynamic-ui-320.png` and `dynamic-ui-expired-pending.png`. They are ignored scratch evidence and are not force-tracked.

Playwright assertion and request-interception syntax was checked against its official [assertions](https://playwright.dev/python/docs/test-assertions) and [network](https://playwright.dev/python/docs/network) documentation; Context7 was unavailable in the tool inventory for this session.
