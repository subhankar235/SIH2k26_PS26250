# Civilian negotiation viewer validation

The read-only monitor now shows the optional contract-net report beside existing scenario evidence. It states that deterministic policies make the decisions and no LLM decides agreement. Settings, message and round budgets, per-request results, accepted/rejected proposal IDs and bids sent are inspectable. The negotiated seed has its own assignment table and served-priority value; the optimizer outcome distinguishes retained seed, refined seed, deterministic fallback and disabled negotiation. Existing final assignments remain visible below it.

The typed peer ledger labels proposals, objections, bids, counterproposals, acceptances and commits. Actor names and message kinds are allowlisted. Entity and finding IDs are restricted to current world entities and canonical specialist findings. Unknown request, candidate or assignment references remove the affected message; malformed slot types and mismatched assignment/candidate IDs are rejected. Proposal references must resolve to a grounded proposal with the canonical run/revision/request/round ID. Assignment-specific rule codes are shown separately from canonical finding IDs. Free text is rendered through `textContent`.

Wrong-run or wrong-revision reports show only an unavailable notice. Expired-pending and unusable snapshots label negotiation activity, seed and outcome as historical. Legacy snapshots without a negotiation report retain the existing view. The viewer adds no mutation controls or API requests.

Run from the repository root:

```powershell
python services/ingestion/scripts/negotiation-ui-fixture.py
python services/ingestion/scripts/relief-ui-fixture.py
python services/ingestion/scripts/dynamic-ui-fixture.py
node --check services/ingestion/web/relief.js
```

Verified in headless Chromium on 2026-10-15:

- Forty typed messages, five policy actors, known candidate assignments and current specialist findings render; unknown actors, kinds, entities, findings, requests, proposals, candidates and assignments are omitted.
- Every report status and outcome label, message budget, seed/final priority, empty messages and missing legacy report render without page errors.
- Untrusted HTML remains literal text. No images, scripts, frames, links, mutation inputs or external write requests are introduced.
- Keyboard disclosure activation, open state, focused summary/table and both scroll offsets survive same-revision refresh, new revisions and automatic timer polling. Removing the current report moves table focus to the simulation heading.
- Wrong-run/revision detail suppression, historical expiry labels, authentication loss and sign-out clear all optional evidence.
- No document overflow at 320, 768, 1024 and 1440 pixels. Wide ledgers remain keyboard-focusable scroll regions. Mobile and desktop captures were visually inspected.

The negative control deliberately serves a copy with the finding filter bypassed:

```powershell
python services/ingestion/scripts/negotiation-ui-fixture.py --mutate-grounding
```

This command must exit nonzero: the `UNKNOWN-FINDING` assertion detects the bypass. The mutation is applied only to the local HTTP response; no source file is changed. The fixture was first run against the original viewer and failed because the negotiation panel did not exist, then passed after implementation.

Screenshots are regenerated in ignored local scratch under `.superpowers/sdd/civilian-negotiation-plan/`: `negotiation-ui-320.png`, `negotiation-ui-1440.png` and `negotiation-ui-historical.png`. They are not force-tracked. The browser fixture uses adversarial synthetic report payloads; live persistence and service-generated negotiation proofs are covered by the service integration validation.

Playwright assertions and local request interception were checked against the official [assertions](https://playwright.dev/python/docs/test-assertions) and [network](https://playwright.dev/python/docs/network) documentation. Context7 was unavailable in this session's tool inventory.
