# Air Power — Decision Intelligence

A ten-page frontend prototype built with Next.js App Router, TypeScript, Tailwind CSS, Recharts, and Lucide icons. All resources are synthetic and generic.

## Run locally

Requires Node.js 22.18+ (Node 24 recommended).

```sh
npm install
npm run dev
```

Open http://localhost:3000. On Windows PowerShell with restricted script execution, use `npm.cmd` instead of `npm`.

```sh
npm run build
npm run typecheck
npm test
```

## Demo workflow

1. Overview: inspect illustrative historical metrics; filter and sort recent records.
2. Data sources: replay a synthetic event and inspect its provenance drawer.
3. Evidence: compare contradictory claims without silently resolving them.
4. Planning: configure resource capacity and horizon, then run the local scheduling heuristic. Try capacity 1 and horizon 4 to see infeasibility.
5. Verification: run independent checks, enter reviewer and reason, then approve or reject.
6. Replanning: change capacity and apply the change. The result becomes stale and cannot be approved until revalidated. Recompute to create a new version.
7. Digital Twin: run seeded fault injection and export measured results.
8. Benchmarks: compare fixture results and inspect locally measured experiment runs.

## Implementation and limits

- `apps/web/app/(platform)/[section]` statically generates all ten routes using one shared application shell.
- `components/store.tsx` persists demo records, plans, experiments, and review history in browser localStorage. This is a single-user demonstration, not authenticated or tamper-proof storage.
- `lib/engine.ts` implements longest-task-first resource scheduling, independent constraint checks, and a seeded detector experiment. It is not OR-Tools and does not claim optimality.
- Historical KPIs, forecasts, model metrics, and reference benchmarks are labeled fixtures. Experiment counts and schedule outcomes are calculated locally. Recovery and production feasibility are not measured by the detector experiment.
- FastAPI, PostgreSQL, Kafka, MLflow, trained forecasting models, authentication, and SSE are not connected. Infrastructure health is shown as unknown.
- Export report downloads a JSON snapshot; experiment export includes seed, fault configuration, code version, time, sample size, and results.

Workspace filters scope the record/event views. Forecasts and historical aggregates retain explicit fixture labels. No real mission, weapon, or operational resource data is used.
