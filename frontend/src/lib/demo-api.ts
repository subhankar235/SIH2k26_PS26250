import type {
  Decision,
  EvidenceIssue,
  Autopsy,
  Forecast,
  Schedule,
  ScheduleDiff,
  StressRun,
  AgentRun,
  AuditEntry,
  StreamStatus,
  FlaggedRecord,
} from "@/types";
import type { ApprovalItem } from "./api/approvals";
import type { VerificationResult } from "./api/verification";
import {
  MOCK_STREAMS,
  MOCK_RECORDS,
  MOCK_DECISIONS,
  MOCK_ISSUES,
  MOCK_FORECAST_POINTS,
  MOCK_BENCHMARKS,
  MOCK_ABLATIONS,
} from "./fixtures";
import { makePlan } from "./engine";
const KEY = "air-power-demo-v1";
interface DemoState {
  version: 1;
  sequence: number;
  decisions: Decision[];
  issues: EvidenceIssue[];
  records: FlaggedRecord[];
  streams: StreamStatus[];
  autopsies: Record<string, Autopsy>;
  forecasts: Forecast[];
  schedules: Schedule[];
  approvals: ApprovalItem[];
  agents: AgentRun[];
  runs: StressRun[];
  audit: AuditEntry[];
  pending: Record<string, number>;
}
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const now = () => new Date().toISOString();
function fail(status: number, message: string): never {
  throw Object.assign(new Error(message), { status, code: "demo_request" });
}
function buildSchedule(
  id: string,
  capacity: number,
  horizon: number,
): Schedule {
  const plan = makePlan(capacity, horizon);
  return {
    id,
    version: 1,
    assignments: plan.assignments.map((a) => ({
      taskId: a.id,
      resourceId: `RES-${a.resource}`,
      start: a.start,
      end: a.end,
    })),
    objectives: {
      utilization: plan.utilization,
      cost: Math.round(1900 + capacity * 475 + horizon * 45),
      balance: Math.max(55, 100 - capacity * 3),
    },
    verification: plan.status === "Feasible" ? "verified" : "invalid",
  };
}
function initial(): DemoState {
  const schedules = [
    buildSchedule("SCH-841", 3, 8),
    buildSchedule("SCH-842", 4, 8),
    buildSchedule("SCH-843", 1, 4),
    buildSchedule("SCH-844", 5, 8),
  ];
  schedules[1].assignments = schedules[1].assignments.filter(
    (a) => a.taskId !== "TSK-105",
  );
  schedules[1].assignments.push({
    taskId: "TSK-106",
    resourceId: "RES-4",
    start: 3,
    end: 5,
  });
  schedules[2].verification = "invalid";
  schedules[3].verification = "uncertain";
  const issues: EvidenceIssue[] = clone(MOCK_ISSUES);
  const records: FlaggedRecord[] = clone(MOCK_RECORDS);
  records[0] = {
    ...records[0],
    status: "Conflict",
    reason: "Registry and telemetry disagree on available capacity",
  };
  records[2] = {
    ...records[2],
    status: "Stale",
    reason: "Registry input is awaiting a refreshed version",
  };
  const autopsies: Record<string, Autopsy> = {};
  issues.forEach((issue, i) => {
    const record = records[i];
    const result: Autopsy = {
      issueId: issue.id,
      issueClass: issue.issueClass,
      claims: [
        {
          id: `CLM-${i + 1}A`,
          attribute: "available_capacity",
          value: `${12 - i * 2} units`,
          sourceId: "SRC-001 Registry",
          observedAt: "2026-10-14T09:40:00Z",
        },
        ...(issue.issueClass === "conflict"
          ? [
              {
                id: `CLM-${i + 1}B`,
                attribute: "available_capacity",
                value: "8 units",
                sourceId: "SRC-002 Telemetry",
                observedAt: "2026-10-14T09:43:00Z",
              },
            ]
          : []),
      ],
      provenance: [
        {
          step: "Source event received and schema validated",
          at: "2026-10-14T09:40:00Z",
          sourceId: issue.sourceId,
        },
        {
          step: `${issue.issueClass} issue detected; linked to ${record.id}`,
          at: "2026-10-14T09:43:00Z",
          sourceId: "Evidence service",
        },
        {
          step: "Dependent decision registered for review",
          at: "2026-10-14T09:44:00Z",
          sourceId: "Validity service",
        },
      ],
      missingInformation:
        issue.issueClass === "duplicate"
          ? []
          : ["Updated source observation", "Analyst reconciliation note"],
      uncertainty: [
        { label: "Source reliability uncertainty", value: 0.08 + i * 0.04 },
        { label: "Observation delay risk", value: 0.14 + i * 0.06 },
      ],
    };
    autopsies[issue.id] = result;
    autopsies[record.id] = { ...result, issueId: record.id };
  });
  autopsies["REC-1047"] = { ...autopsies["ISSUE-02"], issueId: "REC-1047" };
  autopsies["FORECAST-02"] = {
    ...autopsies["ISSUE-04"],
    issueId: "FORECAST-02",
  };
  const decisions: Decision[] = clone(MOCK_DECISIONS).map((decision, i) => ({
    ...decision,
    createdAt: `2026-10-14T0${9 - i}:00:00Z`,
  }));
  const approvals: ApprovalItem[] = [
    {
      id: "APP-901",
      targetId: "SCH-842",
      type: "Dispatch plan",
      status: "pending",
      verification: "verified",
      submittedBy: "Planner Service",
      submittedAt: "2026-10-14T10:15:00Z",
      summary:
        "Verified dispatch schedule for the central sector. Review the assigned resources and reserve margin.",
    },
    {
      id: "APP-902",
      targetId: "SCH-843",
      type: "Contingency plan",
      status: "pending",
      verification: "invalid",
      submittedBy: "Planner Service",
      submittedAt: "2026-10-14T10:05:00Z",
      summary:
        "Insufficient capacity. Approval is blocked; reject with a rationale or create a new plan.",
    },
    {
      id: "APP-903",
      targetId: "SCH-844",
      type: "Reserve allocation",
      status: "pending",
      verification: "uncertain",
      submittedBy: "Planning Agent",
      submittedAt: "2026-10-14T09:55:00Z",
      summary:
        "Awaiting confirmation of reserve availability. This result can be rejected but cannot be approved.",
    },
  ];
  const agents: AgentRun[] = [
    {
      id: "AGENT-401",
      status: "completed",
      query: "Why was DEC-803 invalidated?",
      nodesVisited: [
        "query_parser",
        "evidence_agent",
        "dependency_tracer",
        "verifier",
        "explainer",
      ],
      retries: 1,
      explanation:
        "DEC-803 uses REC-1050 version 2, whose capacity failed range validation. The verifier blocked the dependent contingency plan. Review the contradictory capacity claims before generating a new schedule.",
      evidenceLinks: [
        {
          id: "REC-1050",
          label: "Range validator: capacity check failed",
          version: 2,
        },
        {
          id: "DEC-803",
          label: "Invalidated contingency decision",
          version: 2,
        },
      ],
      createdAt: "2026-10-14T10:20:00Z",
    },
  ];
  const runs: StressRun[] = (
    [
      "clean",
      "heavy_staleness",
      "source_conflict",
      "cascading_changes",
    ] as const
  ).map((scenario, i) => ({
    id: `RUN-${42 + i}`,
    scenario,
    seed: 42 + i,
    faultSeverity: i === 0 ? "low" : "medium",
    status: "completed",
    detectionRate: 98.4 - i * 0.7,
    falseAlarms: i,
    failureRate: i * 1.2,
    feasibility: 100 - i * 1.3,
    recoveryTime: 4 + i * 4.2,
    baseline: 20 + i * 8,
    createdAt: `2026-10-14T0${9 - i}:30:00Z`,
  }));
  const audit: AuditEntry[] = decisions.map((d, i) => ({
    id: `AUD-${i + 1}`,
    entity: d.id,
    action: `Status changed to ${d.status}`,
    actor: "Validity Service",
    timestamp: d.createdAt,
    details: `Recorded dependencies at decision version ${d.version}.`,
    version: d.version,
  }));
  records.forEach((record, i) =>
    audit.push({
      id: `AUD-REC-${i}`,
      entity: `${record.id} ${issues[i % issues.length].id}`,
      action: "Evidence validated",
      actor: "Ingestion Service",
      timestamp: `2026-10-14T09:${String(40 + i).padStart(2, "0")}:00Z`,
      details: record.reason,
      version: record.version,
    }),
  );
  audit.push({
    id: "AUD-REVIEW-1",
    entity: "SCH-841",
    action: "Schedule reviewed",
    actor: "Kathakali Das",
    timestamp: "2026-10-14T10:00:00Z",
    details: "Reserve margin and resource assignments inspected.",
  });
  return {
    version: 1,
    sequence: 1000,
    decisions,
    issues,
    records,
    streams: clone(MOCK_STREAMS),
    autopsies,
    forecasts: [
      {
        id: "FORECAST-01",
        target: "Resource demand",
        points: clone(MOCK_FORECAST_POINTS),
        coverage: 89.4,
        highUncertainty: false,
      },
      {
        id: "FORECAST-02",
        target: "Resource availability under disruption",
        points: MOCK_FORECAST_POINTS.map((p) => ({
          ...p,
          lower: p.mean * 0.55,
          upper: p.mean * 1.5,
        })),
        coverage: 77.2,
        highUncertainty: true,
      },
    ],
    schedules,
    approvals,
    agents,
    runs,
    audit,
    pending: {},
  };
}
let memory: DemoState | undefined;
if (typeof window !== "undefined")
  window.addEventListener("air-power-demo-reset", () => {
    memory = undefined;
  });
function load(): DemoState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as DemoState;
      if (
        parsed.version === 1 &&
        Array.isArray(parsed.decisions) &&
        Array.isArray(parsed.schedules) &&
        parsed.pending
      )
        return parsed;
    }
  } catch {
    /* Fall back to the current in-memory demo when storage is unavailable. */
  }
  return memory ?? initial();
}
function save(state: DemoState) {
  memory = state;
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* Demo actions continue for this page session. */
  }
}
function log(
  state: DemoState,
  entity: string,
  action: string,
  details: string,
  actor = "Demo Service",
) {
  state.audit.unshift({
    id: `AUD-${++state.sequence}`,
    entity,
    action,
    actor,
    timestamp: now(),
    details,
  });
}
function verification(state: DemoState, id: string): VerificationResult {
  const schedule = state.schedules.find((s) => s.id === id);
  const decision = state.decisions.find((d) => d.id === id);
  if (!schedule && !decision) fail(404, "This demo result does not exist.");
  const outcome =
    schedule?.verification ??
    (decision?.status === "verified"
      ? "verified"
      : decision?.status === "invalidated"
        ? "invalid"
        : "uncertain");
  return {
    outcome,
    violations:
      outcome === "invalid"
        ? [
            {
              rule: "resource_capacity",
              message:
                "Available capacity does not meet the schedule requirements.",
              refs: ["REC-1050", "ISSUE-01"],
            },
          ]
        : [],
    uncertainty_flags:
      outcome === "uncertain"
        ? ["Reserve availability has not been confirmed."]
        : [],
  };
}
function diff(old: Schedule, next: Schedule): ScheduleDiff {
  const oldMap = new Map(old.assignments.map((a) => [a.taskId, a]));
  const newMap = new Map(next.assignments.map((a) => [a.taskId, a]));
  const result: ScheduleDiff = {
    added: [],
    removed: [],
    moved: [],
    unchanged: 0,
  };
  for (const a of old.assignments) {
    const b = newMap.get(a.taskId);
    if (!b) result.removed.push(a);
    else if (
      a.resourceId !== b.resourceId ||
      a.start !== b.start ||
      a.end !== b.end
    )
      result.moved.push({ before: a, after: b });
    else result.unchanged++;
  }
  for (const b of next.assignments)
    if (!oldMap.has(b.taskId)) result.added.push(b);
  return result;
}
function advance(state: DemoState) {
  for (const [id, due] of Object.entries(state.pending))
    if (Date.now() >= due) {
      const run = state.runs.find((r) => r.id === id);
      if (run) run.status = "completed";
      const agent = state.agents.find((a) => a.id === id);
      if (agent) {
        agent.status = "completed";
        agent.nodesVisited = [
          "query_parser",
          "evidence_agent",
          "dependency_tracer",
          "verifier",
          "explainer",
        ];
        agent.explanation = `Demo analysis for "${agent.query}": the registry and telemetry disagree on available capacity. REC-1050 version 2 failed the range validator; DEC-803 remains invalidated. SCH-842 passed independent checks and may be reviewed. These are simulated findings from the demo evidence set.`;
      }
      log(
        state,
        id,
        "Run completed",
        "Simulated processing completed and results are available.",
      );
      delete state.pending[id];
    }
}
export async function demoRequest(
  path: string,
  init?: RequestInit,
): Promise<unknown> {
  await new Promise((resolve) => setTimeout(resolve, 180));
  const state = load();
  advance(state);
  const method = init?.method?.toUpperCase() ?? "GET";
  const body =
    typeof init?.body === "string"
      ? (JSON.parse(init.body) as Record<string, unknown>)
      : {};
  const parts = path
    .split("?")[0]
    .split("/")
    .filter(Boolean)
    .map(decodeURIComponent);
  const find = <T extends { id: string }>(rows: T[], id: string): T =>
    rows.find((r) => r.id === id) ??
    fail(404, `Demo record ${id} was not found.`);
  let result: unknown;
  if (path === "/health")
    result = { status: "Demo service ready", service: "AERONIQ demo" };
  else if (path === "/ingestion/status") result = state.streams;
  else if (path === "/ingestion/flagged") result = state.records;
  else if (path === "/evidence/issues") result = state.issues;
  else if (parts[0] === "evidence" && parts[3] === "autopsy")
    result =
      state.autopsies[parts[2]] ??
      fail(404, "This demo evidence record does not exist.");
  else if (path === "/validity/decisions") result = state.decisions;
  else if (parts[0] === "validity" && parts[1] === "decisions")
    result = find(state.decisions, parts[2]);
  else if (path === "/validity/reverify" && method === "POST") {
    const decision = find(state.decisions, String(body.id));
    // Fresh demo observations resolve stale inputs, but failed or missing evidence stays blocked.
    if (decision.status === "stale") {
      decision.status = "verified";
      decision.version++;
      decision.dependencies = decision.dependencies.map((d) => ({
        ...d,
        inputVersion: d.inputVersion + 1,
      }));
    }
    log(
      state,
      decision.id,
      `Re-verified: ${decision.status}`,
      "Stale inputs were refreshed; unresolved invalid or uncertain evidence remains blocked.",
      "Verifier Service",
    );
    result = { success: true, status: decision.status };
  } else if (parts[0] === "forecasts")
    result = find(state.forecasts, parts[1] ?? "FORECAST-01");
  else if (path === "/planning/alternatives")
    result = state.schedules.filter((s) => s.verification === "verified");
  else if (parts[0] === "planning" && parts[1] === "schedules")
    result = find(state.schedules, parts[2]);
  else if (path === "/planning/solve" && method === "POST") {
    const capacity = Number(body.capacity),
      horizon = Number(body.horizon);
    if (
      !Number.isInteger(capacity) ||
      capacity < 1 ||
      capacity > 20 ||
      !Number.isInteger(horizon) ||
      horizon < 1 ||
      horizon > 48
    )
      fail(422, "Use capacity 1-20 and a horizon of 1-48 hours.");
    const schedule = buildSchedule(
      `SCH-${++state.sequence}`,
      capacity,
      horizon,
    );
    state.schedules.unshift(schedule);
    state.approvals.unshift({
      id: `APP-${++state.sequence}`,
      targetId: schedule.id,
      type: "Generated schedule",
      status: "pending",
      verification: schedule.verification,
      submittedBy: "Demo Planner",
      submittedAt: now(),
      summary: `${capacity} resources over ${horizon} hours; ${schedule.verification} result.`,
    });
    log(
      state,
      schedule.id,
      "Schedule generated",
      `Demo solve used capacity ${capacity} and horizon ${horizon}.`,
      "Planner Service",
    );
    result = schedule;
  } else if (parts[0] === "replanning" && parts[1] === "diff")
    result = diff(
      find(state.schedules, parts[2]),
      find(state.schedules, parts[3]),
    );
  else if (path === "/stress/runs" && method === "POST") {
    const scenario = String(body.scenario),
      severity = String(body.faultSeverity),
      seed = Number(body.seed);
    if (
      ![
        "clean",
        "heavy_staleness",
        "source_conflict",
        "cascading_changes",
      ].includes(scenario) ||
      !["low", "medium", "high"].includes(severity) ||
      !Number.isSafeInteger(seed)
    )
      fail(422, "Choose a scenario, severity, and integer seed.");
    const factor = severity === "high" ? 3 : severity === "medium" ? 2 : 1;
    const noise = (Math.abs(seed) % 17) / 10;
    const run: StressRun = {
      id: `RUN-${++state.sequence}`,
      scenario: scenario as StressRun["scenario"],
      seed,
      faultSeverity: severity as StressRun["faultSeverity"],
      status: "running",
      detectionRate:
        scenario === "clean" ? 100 : Number((99 - factor - noise).toFixed(1)),
      falseAlarms: scenario === "clean" ? 0 : factor,
      failureRate:
        scenario === "clean" ? 0 : Number((factor * 0.7 + noise).toFixed(1)),
      feasibility:
        scenario === "clean" ? 100 : Number((100 - factor - noise).toFixed(1)),
      recoveryTime:
        scenario === "clean" ? 0 : Number((factor * 4 + noise).toFixed(1)),
      baseline: scenario === "clean" ? 0 : factor * 15 + noise,
      createdAt: now(),
    };
    state.runs.unshift(run);
    state.pending[run.id] = Date.now() + 2200;
    log(
      state,
      run.id,
      "Stress run launched",
      `${scenario}, seed ${seed}, ${severity} severity.`,
    );
    result = run;
  } else if (path === "/stress/runs") result = state.runs;
  else if (parts[0] === "stress" && parts[1] === "runs")
    result = find(state.runs, parts[2]);
  else if (path === "/agents/requests" && method === "POST") {
    const query = String(body.query ?? "").trim();
    if (!query) fail(422, "Enter a question for the agent.");
    const agent: AgentRun = {
      id: `AGENT-${++state.sequence}`,
      status: "running",
      query,
      nodesVisited: ["query_parser"],
      retries: 0,
      explanation: "Reviewing the demo evidence and verifier results...",
      evidenceLinks: [
        {
          id: "REC-1050",
          label: "Range validator: capacity check failed",
          version: 2,
        },
        { id: "DEC-803", label: "Dependent decision", version: 2 },
      ],
      createdAt: now(),
    };
    state.agents.unshift(agent);
    state.pending[agent.id] = Date.now() + 2200;
    log(state, agent.id, "Agent request started", query);
    result = agent;
  } else if (path === "/agents/requests") result = state.agents;
  else if (parts[0] === "agents" && parts[1] === "requests")
    result = find(state.agents, parts[2]);
  else if (path === "/verification/check")
    result = verification(state, String(body.target_id));
  else if (parts[0] === "verification") result = verification(state, parts[1]);
  else if (path === "/approvals") result = state.approvals;
  else if (
    parts[0] === "approvals" &&
    parts[2] === "decision" &&
    method === "POST"
  ) {
    const approval = find(state.approvals, parts[1]);
    const rationale = String(body.rationale ?? "").trim();
    const reviewer = String(body.reviewer ?? "").trim();
    if (!rationale || !reviewer)
      fail(422, "Reviewer and rationale are required.");
    if (approval.status !== "pending")
      fail(409, "This result has already been reviewed.");
    if (body.decision !== "approved" && body.decision !== "rejected")
      fail(422, "Choose approve or reject.");
    if (
      body.decision === "approved" &&
      verification(state, approval.targetId).outcome !== "verified"
    )
      fail(409, "Only verified results can be approved.");
    approval.status = body.decision;
    log(
      state,
      approval.targetId,
      `Result ${approval.status}`,
      rationale,
      reviewer,
    );
    result = approval;
  } else if (path === "/audit") result = state.audit;
  else if (path === "/benchmarks/results") result = MOCK_BENCHMARKS;
  else if (path === "/benchmarks/ablations") result = MOCK_ABLATIONS;
  else fail(404, "This demo action is not available.");
  save(state);
  return clone(result);
}
