# Air Power — Frontend Guide (Structure + Steps)

Next.js + TypeScript + Tailwind CSS + Recharts dashboard that talks to the FastAPI backend over REST. All data shown is synthetic and non-operational.

---

## 1. Frontend Scope

| Item | Choice |
|---|---|
| Framework | Next.js (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Charts | Recharts |
| API | REST via Fetch |
| Backend | `http://localhost:8000/api/v1` |

**What the dashboard must do**

- Show data ingestion status and flagged records (F1)
- Show contradictions with provenance timeline, the Contradiction Autopsy (F2 · USP 1)
- Show decision validity: verified / stale / invalidated / uncertain (F3 · USP 2)
- Show forecasts with uncertainty bands (F4)
- Show schedules, alternatives, and old-vs-new diffs (F5, F6)
- Launch and view stress-test scenarios (F7 · USP 3)
- Show evidence-cited explanations (F8)
- Provide the human approval queue and audit trail (F9)
- Show baseline and ablation comparisons (F10)

---

## 2. Folder Structure

```
frontend/
├── package.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
├── postcss.config.js
├── .eslintrc.json
├── .env.local.example           # NEXT_PUBLIC_API_URL=http://localhost:8000
├── Dockerfile
├── public/
└── src/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                       # Overview
    │   ├── globals.css
    │   ├── ingestion/page.tsx             # F1
    │   ├── evidence/
    │   │   ├── page.tsx                   # F2 list
    │   │   └── [recordId]/page.tsx        # F2 autopsy
    │   ├── validity/
    │   │   ├── page.tsx                   # F3 list
    │   │   └── [decisionId]/page.tsx      # F3 detail
    │   ├── forecasts/page.tsx             # F4
    │   ├── planning/
    │   │   ├── page.tsx                   # F5
    │   │   └── compare/page.tsx           # F6
    │   ├── stress-lab/
    │   │   ├── page.tsx                   # F7
    │   │   └── [runId]/page.tsx
    │   ├── explanations/page.tsx          # F8
    │   ├── approvals/page.tsx             # F9
    │   ├── audit/page.tsx                 # F9
    │   └── benchmarks/page.tsx            # F10
    ├── components/
    │   ├── ui/                            # Button, Card, Badge, Table, Modal, Spinner, EmptyState, ErrorState
    │   ├── layout/                        # Sidebar, Navbar, PageHeader
    │   ├── charts/                        # UncertaintyBandChart, ScheduleGantt, MetricBarChart, CalibrationPlot
    │   ├── evidence/                      # ProvenanceTimeline, ConflictCard, EvidenceGraph
    │   ├── validity/                      # ValidityBadge, DependencyGraphView
    │   ├── planning/                      # ScheduleDiffView
    │   └── approvals/                     # ApprovalPanel
    ├── lib/
    │   ├── api/                           # client + one file per domain
    │   ├── utils.ts
    │   └── constants.ts
    ├── hooks/                             # useFetch, usePolling, useApproval
    ├── types/                             # TS types mirroring Pydantic schemas
    └── styles/theme.ts
```

---

## 3. Step-by-Step Frontend Build

### Step 1 — Create the app

```bash
cd air-power
npx create-next-app@latest frontend --typescript --tailwind --app --eslint --src-dir
cd frontend
npm install recharts
```

### Step 2 — Environment

`.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

Copy to `.env.local.example` (without secrets) and commit that.

### Step 3 — API client

`src/lib/api/client.ts`:

```ts
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.code ?? "unknown", body.message ?? res.statusText, body.details);
  }
  return res.json() as Promise<T>;
}
```

Create one file per domain (`ingestion.ts`, `evidence.ts`, `validity.ts`, `forecasts.ts`, `planning.ts`, `stress.ts`, `agents.ts`, `verification.ts`, `benchmarks.ts`) that wraps `api()` with typed functions.

### Step 4 — Types (mirror the backend)

`src/types/`:

```ts
// validity.ts
export type ValidityStatus = "verified" | "stale" | "invalidated" | "uncertain";

export interface Decision {
  id: string;
  type: string;
  version: number;
  status: ValidityStatus;
  createdAt: string;
  assumptions: { id: string; description: string }[];
  dependencies: { inputId: string; inputVersion: number }[];
}
```

```ts
// evidence.ts
export type IssueClass = "stale" | "missing" | "duplicate" | "conflict";

export interface Claim {
  id: string; attribute: string; value: string;
  sourceId: string; observedAt: string; supersededBy?: string | null;
}

export interface Autopsy {
  issueId: string;
  issueClass: IssueClass;
  claims: Claim[];
  provenance: { step: string; at: string; sourceId: string }[];
  missingInformation: string[];
  uncertainty: { label: string; value: number }[];
}
```

```ts
// forecast.ts
export interface ForecastPoint { t: string; mean: number; lower: number; upper: number; }
export interface Forecast { id: string; target: string; points: ForecastPoint[]; coverage?: number; highUncertainty: boolean; }
```

```ts
// schedule.ts
export interface Assignment { taskId: string; resourceId: string; start: number; end: number; }
export interface Schedule { id: string; version: number; assignments: Assignment[]; objectives: Record<string, number>; verification: "verified" | "invalid" | "uncertain"; }
export interface ScheduleDiff { added: Assignment[]; removed: Assignment[]; moved: { before: Assignment; after: Assignment }[]; unchanged: number; }
```

Also create `stress.ts`, `audit.ts`, `index.ts`. Keep types in parity with Pydantic schemas (a contract test in `tests/contract/` checks this).

### Step 5 — Layout and shared UI

1. `components/layout/Sidebar.tsx` — links to all 11 routes.
2. `components/layout/PageHeader.tsx` — title + description + actions.
3. `components/ui/` — Button, Card, Table, Modal, Spinner, `EmptyState`, `ErrorState`.
4. `components/validity/ValidityBadge.tsx` — consistent colours and labels for the four statuses.

```tsx
const STYLES: Record<ValidityStatus, string> = {
  verified: "bg-green-100 text-green-800",
  stale: "bg-yellow-100 text-yellow-800",
  invalidated: "bg-red-100 text-red-800",
  uncertain: "bg-gray-200 text-gray-800",
};

export function ValidityBadge({ status }: { status: ValidityStatus }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>{status}</span>;
}
```

5. Wire `app/layout.tsx` with the sidebar and a content area.

### Step 6 — Hooks

- `useFetch<T>(fn, deps)` → `{ data, error, loading, refetch }`
- `usePolling(fn, intervalMs)` → for agent run and stress-run status
- `useApproval()` → submit approve/reject with rationale

### Step 7 — Build pages in this order

#### 7.1 Overview `/`
- Counts by validity status
- Recent flagged records
- Pending approvals
- Backend health

#### 7.2 Ingestion `/ingestion` (F1)
- Stream status cards per topic
- Validation error counts
- Flagged records table with reason column

#### 7.3 Evidence `/evidence` and `/evidence/[recordId]` (F2 · USP 1)
- Issue list filterable by class (stale / missing / duplicate / conflict)
- **Autopsy page:**
  - `ConflictCard` for each competing claim (value, source, timestamp)
  - `ProvenanceTimeline` showing origin and change history
  - "Missing information" list
  - Uncertainty values
  - Link to related audit entries

#### 7.4 Validity `/validity` and `/validity/[decisionId]` (F3 · USP 2)
- Table of decisions with `ValidityBadge`
- Detail page: assumptions, input versions, `DependencyGraphView`, status-change history
- "Re-verify" button → `POST /validity/reverify`

#### 7.5 Forecasts `/forecasts` (F4)
- `UncertaintyBandChart` (Recharts `ComposedChart`: line for mean, `Area` for the band)
- Calibration indicator (coverage vs nominal)
- Warning banner when `highUncertainty` is true

```tsx
<ComposedChart data={points}>
  <XAxis dataKey="t" /><YAxis /><Tooltip />
  <Area dataKey="upper" stroke="none" fillOpacity={0.15} />
  <Area dataKey="lower" stroke="none" fill="#fff" fillOpacity={1} />
  <Line dataKey="mean" dot={false} strokeWidth={2} />
</ComposedChart>
```

(For a true band, store `[lower, upper]` as a range value and use a single `Area`.)

#### 7.6 Planning `/planning` and `/planning/compare` (F5, F6)
- Form to submit a solve request
- `ScheduleGantt` (custom bar layout or stacked `BarChart`)
- Objective trade-off chart across alternatives
- Verification badge on each schedule
- **Compare page:** `ScheduleDiffView` showing added / removed / moved / unchanged, plus change-impact summary

#### 7.7 Stress Lab `/stress-lab` (F7 · USP 3)
- Scenario picker (clean, heavy staleness, source conflict, cascading changes), seed input, fault severity
- Launch → poll run status with `usePolling`
- Results page: detection rate, false alarms, failure rate, feasibility, recovery time vs baseline (`MetricBarChart`)

#### 7.8 Explanations `/explanations` (F8)
- Agent run list and status
- Explanation text with **evidence links** (record IDs, versions, validator results)
- Agent trace (nodes visited, retries)

#### 7.9 Approvals `/approvals` (F9)
- Queue of results awaiting review
- `ApprovalPanel`: shows schedule, evidence, uncertainty flags, verifier output
- Approve / reject with required rationale
- Only `verified` results can be approved

#### 7.10 Audit `/audit` (F9)
- Searchable, filterable table (entity, action, actor, time)
- Read-only; no edit or delete controls

#### 7.11 Benchmarks `/benchmarks` (F10)
- Full system vs baselines (`MetricBarChart`)
- Ablation table
- Statistical results: effect sizes and confidence intervals
- `CalibrationPlot` for forecast calibration

### Step 8 — UI rules (apply everywhere)

1. Show **uncertainty next to every prediction**.
2. Every recommendation has a **"View evidence"** link.
3. Use `ValidityBadge` for all four statuses, consistently.
4. Provide **loading, empty, and error** states on every view.
5. Never offer edit or delete for audit entries.
6. Disable approval for anything not `verified`.
7. Keyboard-accessible controls, sufficient contrast, semantic labels.
8. Desktop-first, usable on tablet.

### Step 9 — Run and verify

```bash
npm run dev          # http://localhost:3000
```

Make sure the backend is running at `http://localhost:8000`. Enable CORS in FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])
```

### Step 10 — Quality checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Optional: component tests with Vitest/Jest + React Testing Library for `ValidityBadge`, `ApprovalPanel`, and `ScheduleDiffView`.

### Step 11 — Dockerise

`frontend/Dockerfile` (multi-stage: install → build → run). Add the `frontend` service to the root `docker-compose.yml`:

```yaml
frontend:
  build: ./frontend
  ports: ["3000:3000"]
  environment:
    NEXT_PUBLIC_API_URL: http://localhost:8000/api/v1
  depends_on: [backend]
```

---

## 4. Page → Endpoint Map

| Page | Feature | Endpoints used |
|---|---|---|
| `/` | All | `GET /health`, `GET /validity/decisions`, `GET /ingestion/flagged`, `GET /approvals` |
| `/ingestion` | F1 | `GET /ingestion/status`, `GET /ingestion/flagged` |
| `/evidence` | F2 | `GET /evidence/issues` |
| `/evidence/[recordId]` | F2 | `GET /evidence/issues/{id}/autopsy`, `GET /evidence/provenance/{record_id}` |
| `/validity` | F3 | `GET /validity/decisions` |
| `/validity/[decisionId]` | F3 | `GET /validity/decisions/{id}`, `POST /validity/reverify` |
| `/forecasts` | F4 | `POST /forecasts`, `GET /forecasts/{id}` |
| `/planning` | F5 | `POST /planning/solve`, `GET /planning/schedules/{id}`, `GET /planning/alternatives` |
| `/planning/compare` | F6 | `POST /replanning/run`, `GET /replanning/diff/{old}/{new}` |
| `/stress-lab` | F7 | `POST /stress/runs`, `GET /stress/runs/{id}` |
| `/explanations` | F8 | `POST /agents/requests`, `GET /agents/requests/{id}`, `GET /agents/requests/{id}/explanation` |
| `/approvals` | F9 | `GET /approvals`, `POST /approvals/{id}/decision`, `POST /verification/check` |
| `/audit` | F9 | `GET /audit`, `GET /audit/{entity}/{id}` |
| `/benchmarks` | F10 | `GET /benchmarks/results`, `GET /benchmarks/ablations` |

---

## 5. Component → Used By

| Component | Used on |
|---|---|
| `ValidityBadge` | Overview, Validity, Approvals, Planning |
| `UncertaintyBandChart` | Forecasts, Explanations |
| `ProvenanceTimeline` | Evidence autopsy |
| `ConflictCard` | Evidence autopsy |
| `EvidenceGraph` | Evidence autopsy |
| `DependencyGraphView` | Validity detail |
| `ScheduleGantt` | Planning |
| `ScheduleDiffView` | Planning compare |
| `MetricBarChart` | Stress Lab, Benchmarks |
| `CalibrationPlot` | Forecasts, Benchmarks |
| `ApprovalPanel` | Approvals |

---

## 6. Frontend Build Order (Summary)

```
Create app → env → API client → types → layout + shared UI → hooks
→ Overview → Ingestion → Evidence + Autopsy → Validity
→ Forecasts → Planning + Compare → Stress Lab
→ Explanations → Approvals → Audit → Benchmarks
→ CORS + run → lint/type/build → Docker
```

**Tip:** build each page right after its backend endpoint exists. Until then, use mock data matching the types so the UI work isn't blocked.
