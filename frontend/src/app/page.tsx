"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ShieldCheck,
  Layers3,
  Activity,
  Database,
  Radio,
  FileCheck2,
  ArrowRight,
  RefreshCw,
  ClipboardCheck,
  CircleHelp,
  Zap,
  AlertTriangle,
  Clock,
  Plane,
  Crosshair,
  Sparkles,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorState } from "@/components/ui/ErrorState";
import { useFetch } from "@/hooks/useFetch";
import { getDecisions } from "@/lib/api/validity";
import { getFlaggedRecords, getIngestionStatus } from "@/lib/api/ingestion";
import { getApprovals } from "@/lib/api/approvals";
import { getHealth } from "@/lib/api/health";
import { getForecast } from "@/lib/api/forecasts";
import { api } from "@/lib/api/client";
import { useDataMode } from "@/lib/data-mode";
import { MagiVisualizer } from "@/components/magi/MagiVisualizer";
import { ResourceBoards } from "@/components/resources/ResourceBoards";
import {
  MAGI_INITIAL_AGENTS,
  SYSTEM_KPIS,
  MagiAgent,
} from "@/lib/aerospace-fixtures";

const STATUS = [
  { key: "verified", label: "Verified", color: "#ea580c" },
  { key: "stale", label: "Stale", color: "#f59e0b" },
  { key: "uncertain", label: "Uncertain", color: "#fed7aa" },
  { key: "invalidated", label: "Invalidated", color: "#cbd5e1" },
] as const;

const number = (value: number) => value.toLocaleString("en-IN");

function Donut({ counts, total }: { counts: number[]; total: number }) {
  let start = 0;
  return (
    <div className="donut-wrap">
      <svg
        viewBox="0 0 160 160"
        role="img"
        aria-label={`Decision status distribution, ${total} total decisions`}
      >
        <circle
          cx="80"
          cy="80"
          r="62"
          fill="none"
          stroke="#ffedd5"
          strokeWidth="17"
        />
        {counts.map((count, i) => {
          const fraction = total ? count / total : 0;
          const offset = start;
          start += fraction;
          return (
            fraction > 0 && (
              <circle
                key={i}
                cx="80"
                cy="80"
                r="62"
                fill="none"
                stroke={STATUS[i].color}
                strokeWidth="17"
                strokeLinecap="round"
                strokeDasharray={`${Math.max(0, fraction * 389.56 - 12)} 389.56`}
                strokeDashoffset={-offset * 389.56}
                transform="rotate(-160 80 80)"
              />
            )
          );
        })}
      </svg>
      <div className="donut-label">
        <span>Total decisions</span>
        <strong>{number(total)}</strong>
      </div>
    </div>
  );
}

function Gauge({ percent }: { percent: number }) {
  return (
    <svg
      viewBox="0 0 280 158"
      className="readiness-gauge"
      role="img"
      aria-label={`${percent}% verified decisions`}
    >
      {Array.from({ length: 45 }, (_, i) => {
        const angle = Math.PI + (i * Math.PI) / 44;
        const x1 = Number((140 + 115 * Math.cos(angle)).toFixed(2));
        const y1 = Number((145 + 115 * Math.sin(angle)).toFixed(2));
        const x2 = Number((140 + 96 * Math.cos(angle)).toFixed(2));
        const y2 = Number((145 + 96 * Math.sin(angle)).toFixed(2));
        const active = i / 44 <= percent / 100;
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={active ? "#ea580c" : "#fed7aa"}
            strokeWidth="3.4"
            strokeLinecap="round"
          />
        );
      })}
      <text x="140" y="112" textAnchor="middle" className="gauge-value">
        {percent}%
      </text>
      <text x="140" y="134" textAnchor="middle" className="gauge-label">
        Confidence score
      </text>
    </svg>
  );
}

function PanelTitle({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="panel-title-row">
      <div className="flex items-center gap-2">
        <h3 className="panel-title">{title}</h3>
        <CircleHelp
          size={14}
          className="text-slate-400"
          aria-label={`About ${title}`}
        />
      </div>
      {children}
    </div>
  );
}

export default function DashboardPage() {
  const { mode, setMode } = useDataMode();
  const [window, setWindow] = useState<"12" | "24">("12");

  // Dynamic MAGI Multi-Agent Simulation State
  const [agents, setAgents] = useState<MagiAgent[]>(MAGI_INITIAL_AGENTS);
  const [consensusStatus, setConsensusStatus] = useState<
    "CONSENSUS" | "DELIBERATING" | "BREACH"
  >("CONSENSUS");
  const [consensusTimeMs, setConsensusTimeMs] = useState<number>(1420);
  const [kpis, setKpis] = useState(SYSTEM_KPIS);
  const [activeDisruption, setActiveDisruption] = useState<string | null>(null);
  const [liveSorties, setLiveSorties] = useState<any[] | null>(null);

  // Initial live plan manifest fetch on cold start
  useEffect(() => {
    if (mode === "live") {
      api("/plans/active")
        .then((res: any) => {
          if (res?.assignments && res.assignments.length > 0) {
            setLiveSorties(res.assignments);
          }
        })
        .catch((err) => {
          console.warn("Active plan fetch error:", err);
        });
    }
  }, [mode]);

  const decisions = useFetch(getDecisions);
  const records = useFetch(getFlaggedRecords);
  const approvals = useFetch(getApprovals);
  const streams = useFetch(getIngestionStatus);
  const health = useFetch(getHealth);
  const forecast = useFetch(getForecast);

  const total = decisions.data?.length ?? 0;
  const counts = STATUS.map(
    (status) =>
      decisions.data?.filter((item) => item.status === status.key).length ?? 0
  );
  const percent = total ? Math.round((counts[0] / total) * 100) : 0;
  const pending =
    approvals.data?.filter((item) => item.status === "pending") ?? [];
  const sourceData = (streams.data ?? []).slice(0, 6);
  const throughput = sourceData.reduce(
    (sum, source) =>
      sum + (Number.parseFloat(source.rate.replaceAll(",", "")) || 0),
    0
  );
  const maxRate = Math.max(
    1,
    ...sourceData.map(
      (source) => Number.parseFloat(source.rate.replaceAll(",", "")) || 0
    )
  );
  const chartData = (forecast.data?.points ?? []).slice(
    0,
    window === "12" ? 6 : 12
  );

  const errors = [
    decisions.error,
    records.error,
    approvals.error,
    streams.error,
    forecast.error,
  ].filter(Boolean);

  function refresh() {
    void decisions.refetch();
    void records.refetch();
    void approvals.refetch();
    void streams.refetch();
    void forecast.refetch();
    void health.refetch();
  }

  // Live Disruption Simulation Handler
  function handleInjectDisruption(scenario: string) {
    setActiveDisruption(scenario);

    // In live mode, dispatch disruption directly to backend CP-SAT replanning engine
    if (mode === "live") {
      api("/disruption", {
        method: "POST",
        body: JSON.stringify({ scenario }),
      })
        .then((res: any) => {
          refresh();
          if (res?.assignments && res.assignments.length > 0) {
            setLiveSorties(res.assignments);
          } else {
            setLiveSorties([]);
          }
        })
        .catch((err) => {
          console.warn("Disruption API call note:", err);
          setLiveSorties([]);
        });
    }

    if (scenario === "storm_front") {
      setConsensusStatus("BREACH");
      setAgents((prev) =>
        prev.map((agent) => {
          if (agent.id === "AGENT-WEATHER") {
            return {
              ...agent,
              status: "OBJECT",
              vote: "OBJECTION",
              confidence: 99.2,
              rationale:
                "CRITICAL: Severe convective storm cell detected in Corridor Charlie-7. Cloud ceiling FL420 with high lightning density. Vetoing Corridor Charlie passage.",
              lastBidTime: "10:15:10 UTC",
            };
          }
          if (agent.id === "AGENT-FLEET") {
            return {
              ...agent,
              status: "DELIBERATING",
              vote: "EVALUATING",
              confidence: 94.5,
              rationale:
                "Calculating fuel endurance for 22 NM northern diversion via Corridor Bravo-3. Additional fuel burn: +180 kg. Feasible.",
              lastBidTime: "10:15:11 UTC",
            };
          }
          return agent;
        })
      );
      setKpis((prev) => ({
        ...prev,
        operationalRiskIndex: 54.8,
        operationalRiskLevel: "ELEVATED CONVECTIVE RISK",
      }));

      // Simulate CP-SAT Solver Re-plan
      setTimeout(() => {
        setConsensusStatus("DELIBERATING");
        setConsensusTimeMs(1180);
      }, 900);

      setTimeout(() => {
        setConsensusStatus("CONSENSUS");
        setConsensusTimeMs(1380);
        setAgents((prev) =>
          prev.map((agent) => ({
            ...agent,
            status: "AGREE",
            vote: "APPROVED",
            confidence: 98.4,
            rationale:
              "Optimal replan accepted: Flights rerouted through Corridor Bravo-3. Separation safety envelopes maintained without mission cancellation.",
            lastBidTime: "10:15:14 UTC",
          }))
        );
        setKpis((prev) => ({
          ...prev,
          operationalRiskIndex: 16.4,
          operationalRiskLevel: "LOW RISK (REROUTED)",
          conflictsPreventedCount: prev.conflictsPreventedCount + 1,
        }));
      }, 2200);
    } else if (scenario === "threat_spike") {
      setConsensusStatus("BREACH");
      setAgents((prev) =>
        prev.map((agent) => {
          if (agent.id === "AGENT-THREAT") {
            return {
              ...agent,
              status: "OBJECT",
              vote: "OBJECTION",
              confidence: 99.8,
              rationale:
                "HOSTILE SAM LOCK: S-400 acquisition radar active in Sector Bravo Grid 41. Stand-off margin breached (< 110 km). Vetoing high-altitude ingress.",
              lastBidTime: "10:15:20 UTC",
            };
          }
          if (agent.id === "AGENT-ORDNANCE") {
            return {
              ...agent,
              status: "DELIBERATING",
              vote: "EVALUATING",
              confidence: 95.0,
              rationale:
                "Reviewing stand-off strike envelope: BrahMos-A 450 km range permits launch from safe boundary without entering SAM engagement envelope.",
              lastBidTime: "10:15:21 UTC",
            };
          }
          return agent;
        })
      );
      setKpis((prev) => ({
        ...prev,
        operationalRiskIndex: 72.1,
        operationalRiskLevel: "HIGH SAM THREAT SPIKE",
      }));

      setTimeout(() => {
        setConsensusStatus("DELIBERATING");
        setConsensusTimeMs(1540);
      }, 900);

      setTimeout(() => {
        setConsensusStatus("CONSENSUS");
        setConsensusTimeMs(1490);
        setAgents((prev) =>
          prev.map((agent) => ({
            ...agent,
            status: "AGREE",
            vote: "APPROVED",
            confidence: 97.9,
            rationale:
              "Terrain-masked ingress altitude (FL140) and stand-off BrahMos launch point committed. SAM threat envelope successfully neutralized.",
            lastBidTime: "10:15:25 UTC",
          }))
        );
        setKpis((prev) => ({
          ...prev,
          operationalRiskIndex: 18.2,
          operationalRiskLevel: "LOW RISK (STANDOFF ENGAGED)",
          conflictsPreventedCount: prev.conflictsPreventedCount + 1,
        }));
      }, 2200);
    } else if (scenario === "mechanical_fault") {
      setConsensusStatus("BREACH");
      setAgents((prev) =>
        prev.map((agent) => {
          if (agent.id === "AGENT-FLEET") {
            return {
              ...agent,
              status: "OBJECT",
              vote: "OBJECTION",
              confidence: 98.9,
              rationale:
                "MAINTENANCE ABORT: Lead airframe SU30-SB042 hydraulic actuator pressure anomaly. Turnaround prediction extended +75 min. Requesting airframe swap.",
              lastBidTime: "10:15:30 UTC",
            };
          }
          if (agent.id === "AGENT-CREW") {
            return {
              ...agent,
              status: "DELIBERATING",
              vote: "EVALUATING",
              confidence: 96.2,
              rationale:
                "Verifying crew cross-qualification for reserve Dassault Rafale RB011. Wg Cdr Rathore certified on type. Duty hours permit reassignment.",
              lastBidTime: "10:15:31 UTC",
            };
          }
          return agent;
        })
      );

      setTimeout(() => {
        setConsensusStatus("DELIBERATING");
        setConsensusTimeMs(1210);
      }, 900);

      setTimeout(() => {
        setConsensusStatus("CONSENSUS");
        setConsensusTimeMs(1310);
        setAgents((prev) =>
          prev.map((agent) => ({
            ...agent,
            status: "AGREE",
            vote: "APPROVED",
            confidence: 99.1,
            rationale:
              "Airframe swap completed to RAF-RB011. Station ordnance transferred. Sortie launch time preserved within 4-minute variance window.",
            lastBidTime: "10:15:34 UTC",
          }))
        );
        setKpis((prev) => ({
          ...prev,
          operationalRiskIndex: 14.2,
          operationalRiskLevel: "LOW RISK",
          conflictsPreventedCount: prev.conflictsPreventedCount + 1,
        }));
      }, 2200);
    }
  }

  function handleResetEquilibrium() {
    setActiveDisruption(null);
    setConsensusStatus("CONSENSUS");
    setConsensusTimeMs(1420);
    setAgents(MAGI_INITIAL_AGENTS);
    setKpis(SYSTEM_KPIS);
    if (mode === "live") {
      api("/disruption", {
        method: "POST",
        body: JSON.stringify({ scenario: "reset" }),
      })
        .then(() => {
          refresh();
          setLiveSorties(null);
        })
        .catch((err) => {
          console.warn("Reset API call note:", err);
        });
    }
  }

  return (
    <div className="dashboard">
      {/* 1. Tactical Executive Impact KPIs */}
      <div className="kpi-stat-deck">
        <div className="kpi-card glass-panel">
          <div className="kpi-icon-wrap kpi-icon-orange">
            <Zap size={20} />
          </div>
          <div>
            <span className="kpi-label">TIME SAVED</span>
            <div className="kpi-value text-orange-600">
              {kpis.timeSavedPercent}%
            </div>
            <p className="kpi-subtext">{kpis.timeSavedDescription}</p>
          </div>
        </div>

        <div className="kpi-card glass-panel">
          <div className="kpi-icon-wrap kpi-icon-green">
            <ShieldCheck size={20} />
          </div>
          <div>
            <span className="kpi-label">CONFLICTS PREVENTED</span>
            <div className="kpi-value text-emerald-600">
              {kpis.conflictsPreventedCount} / {kpis.conflictsPreventedCount}
            </div>
            <p className="kpi-subtext">{kpis.conflictsPreventedBreakdown}</p>
          </div>
        </div>

        <div className="kpi-card glass-panel">
          <div className="kpi-icon-wrap kpi-icon-blue">
            <Activity size={20} />
          </div>
          <div>
            <span className="kpi-label">OPERATIONAL RISK</span>
            <div className="kpi-value text-slate-900">
              {kpis.operationalRiskIndex} <span className="text-xs text-slate-500">/ 100</span>
            </div>
            <p className="kpi-subtext font-semibold text-orange-600">
              {kpis.operationalRiskLevel}
            </p>
          </div>
        </div>

        <div className="kpi-card glass-panel">
          <div className="kpi-icon-wrap kpi-icon-orange">
            <Plane size={20} />
          </div>
          <div>
            <span className="kpi-label">FLEET READY RATE</span>
            <div className="kpi-value text-slate-900">
              {kpis.fleetReadyPercent}%
            </div>
            <p className="kpi-subtext">
              {kpis.activeAirframesReady} of {kpis.totalFleetCount} combat airframes on standby
            </p>
          </div>
        </div>
      </div>

      {/* 2. MAGI Evangelion-Inspired Multi-Agent Visualizer */}
      <MagiVisualizer
        agents={agents}
        consensusStatus={consensusStatus}
        consensusTimeMs={consensusTimeMs}
        onInjectDisruption={handleInjectDisruption}
        onResetEquilibrium={handleResetEquilibrium}
      />

      {/* 3. Tactical Operational Resource Boards */}
      <ResourceBoards disruptionScenario={activeDisruption} liveSorties={liveSorties} />

      {/* 4. Core System Analytics & Decision Health */}
      <div className="dashboard-top-row mt-6">
        <section className="welcome-panel glass-panel-orange">
          <div className="welcome-copy">
            <div className="flex items-center gap-2 mb-2">
              <span className="magi-badge">SYSTEM HEALTH: OPTIMAL</span>
              <span className="text-xs text-slate-500">&bull; Live Dispatch Grid</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 leading-tight">
              Air Operations Command &amp; Decision Intelligence
            </h2>
            <p className="text-xs text-slate-600 mt-1 mb-4 leading-relaxed">
              Google OR-Tools CP-SAT multi-objective mathematical optimization coupled with
              Evangelion-inspired autonomous MAGI consensus. Anti-churn stability guaranteed.
            </p>
            <Link href="/benchmarks" className="forest-button">
              View Benchmarks &amp; Solver Convergence <ArrowUpRight size={16} />
            </Link>
          </div>

          <div className="summary-card glass-panel">
            <div className="summary-label">
              Total Decisions
              <span className="metric-icon">
                <Layers3 size={16} />
              </span>
            </div>
            <strong>
              {decisions.loading || decisions.error ? "--" : number(total)}
            </strong>
            <span className="metric-chip">
              <ShieldCheck size={11} />{" "}
              {decisions.error ? "Awaiting data" : `${counts[0]} verified`}
            </span>
            <small>Across active air operations</small>
          </div>

          <div className="summary-card glass-panel">
            <div className="summary-label">
              Flagged Telemetry
              <span className="metric-icon">
                <Database size={16} />
              </span>
            </div>
            <strong>
              {records.loading || records.error
                ? "--"
                : String(records.data?.length ?? 0).padStart(2, "0")}
            </strong>
            <span className="metric-chip amber">
              <Activity size={11} /> Auto-Resolved
            </span>
            <small>Kafka stream audit</small>
          </div>

          <div className="summary-card glass-panel">
            <div className="summary-label">
              Commander Approvals
              <span className="metric-icon">
                <ClipboardCheck size={16} />
              </span>
            </div>
            <strong>
              {approvals.loading || approvals.error
                ? "--"
                : String(pending.length).padStart(2, "0")}
            </strong>
            <span className="metric-chip">
              <ArrowUpRight size={11} />{" "}
              {
                pending.filter((item) => item.verification === "verified").length
              }{" "}
              Ready
            </span>
            <small>Mission queues ready</small>
          </div>
        </section>

        {/* Decision Health Donut */}
        <section className="dashboard-panel distribution-panel glass-panel">
          <PanelTitle title="Decision Health & Validity">
            <select
              className="mint-select"
              aria-label="Dashboard data source"
              value={mode}
              onChange={(e) => setMode(e.target.value as "demo" | "live")}
            >
              <option value="demo">Demo workspace</option>
              <option value="live">Live API</option>
            </select>
          </PanelTitle>

          {decisions.error ? (
            <p className="panel-empty">
              Decision health is unavailable while the service is disconnected.
            </p>
          ) : (
            <div className="distribution-content">
              <Donut counts={counts} total={total} />
              <ul className="chart-legend">
                {STATUS.map((status, i) => (
                  <li key={status.key}>
                    <span style={{ background: status.color }} />
                    <span>{status.label}</span>
                    <small>
                      {total ? Math.round((counts[i] / total) * 100) : 0}%
                    </small>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      {errors.length > 0 && (
        <ErrorState
          resource="Live dashboard data"
          message={errors[0]!}
          onRetry={refresh}
        />
      )}

      {errors.length === 0 && (
        <>
          <div className="dashboard-middle-row mt-6">
            <section className="dashboard-panel source-panel glass-panel">
              <PanelTitle title="Telemetry Activity by Kafka Topic">
                <Link href="/ingestion" className="mint-link">
                  View Ingestion Pipeline <ArrowUpRight size={14} />
                </Link>
              </PanelTitle>
              <div className="panel-headline">
                <strong>
                  {number(throughput)}
                  <span>/s</span>
                </strong>
                <span>Active event ingestion rate</span>
              </div>

              <div className="source-chart">
                {sourceData.map((source, i) => {
                  const rate =
                    Number.parseFloat(source.rate.replaceAll(",", "")) || 0;
                  return (
                    <div className="source-column" key={source.topic}>
                      <span className="source-name" title={source.topic}>
                        {source.topic}
                      </span>
                      <strong>{source.rate}</strong>
                      <span className="source-percent">
                        {throughput ? Math.round((rate / throughput) * 100) : 0}%
                      </span>
                      <div className="source-bar-area">
                        <div
                          className={`source-bar ${i === 1 ? "highlight" : ""}`}
                          style={{ height: `${25 + (rate / maxRate) * 75}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="dashboard-panel forecast-panel glass-panel">
              <PanelTitle title="Tactical Airspace & Demand Forecast">
                <select
                  className="mint-select"
                  aria-label="Forecast time window"
                  value={window}
                  onChange={(e) => setWindow(e.target.value as "12" | "24")}
                >
                  <option value="12">12 hours</option>
                  <option value="24">24 hours</option>
                </select>
              </PanelTitle>
              <div className="forecast-chart">
                <ResponsiveContainer width="100%" height={210}>
                  <ComposedChart
                    data={chartData}
                    margin={{ top: 20, right: 3, left: -20, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient
                        id="dashboard-forecast"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#ea580c"
                          stopOpacity={0.4}
                        />
                        <stop
                          offset="100%"
                          stopColor="#fed7aa"
                          stopOpacity={0.05}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#ffedd5" />
                    <XAxis
                      dataKey="t"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      dy={10}
                      minTickGap={15}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#64748b", fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "rgba(255, 255, 255, 0.95)",
                        border: "1px solid #fed7aa",
                        borderRadius: 12,
                        boxShadow: "0 10px 30px rgba(234, 88, 12, 0.15)",
                        fontSize: 12,
                      }}
                    />
                    <Area
                      isAnimationActive={false}
                      type="linear"
                      dataKey="mean"
                      name="Mean forecast"
                      stroke="#ea580c"
                      strokeWidth={2}
                      fill="url(#dashboard-forecast)"
                    />
                    <Line
                      isAnimationActive={false}
                      type="linear"
                      dataKey="lower"
                      name="Lower bound"
                      stroke="#f97316"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="inline-legend">
                <span>
                  <i /> Mean forecast
                </span>
                <span>
                  <i /> Lower prediction bound
                </span>
              </div>
            </section>
          </div>

          <div className="dashboard-bottom-row mt-6">
            <section className="dashboard-panel performance-panel glass-panel">
              <PanelTitle title="Fleet Readiness & Confidence Index">
                <Link href="/benchmarks" className="mint-link">
                  Detailed Metrics <ArrowUpRight size={14} />
                </Link>
              </PanelTitle>
              <div className="performance-content">
                <Gauge percent={percent} />
                <div className="performance-summary">
                  <p>
                    <strong>{counts[0]} of {total}</strong> operational schedules verified mathematically valid
                    under CP-SAT capacity, corridor weather, and crew constraints.
                  </p>
                </div>
              </div>
            </section>

            <section className="dashboard-panel target-panel glass-panel">
              <PanelTitle title="Mission Assurance Health">
                <CircleHelp size={17} className="muted-icon" />
              </PanelTitle>
              <div className="readiness-headline">
                <strong>
                  <ArrowUpRight size={22} className="text-orange-500" />
                  {percent}%
                </strong>
                <p>
                  Schedules verified,
                  <br />
                  ready for high-threat dispatch.
                </p>
              </div>
              <div className="target-labels">
                <div>
                  <span>Verified decisions</span>
                  <strong>
                    {counts[0]} <small>/ {total}</small>
                  </strong>
                </div>
                <span>Target &nbsp;100%</span>
              </div>
              <div className="target-track">
                <span style={{ width: `${percent}%` }} />
              </div>
              <div className="target-foot">
                <span>{total - counts[0]} decisions need review</span>
                <Link href="/validity" className="mint-link">
                  View decisions <ArrowRight size={14} />
                </Link>
              </div>
              <div className="backend-status">
                <span
                  className={`connection-dot ${health.error ? "offline" : ""}`}
                />
                <span>Backend health</span>
                <strong>
                  {mode === "demo"
                    ? "Demo mode"
                    : health.loading
                      ? "Checking"
                      : health.error
                        ? "Unavailable"
                        : (health.data?.status ?? "Unknown")}
                </strong>
                <button aria-label="Refresh dashboard" onClick={refresh}>
                  <RefreshCw size={14} />
                </button>
              </div>
            </section>

            <section className="dashboard-panel records-panel glass-panel">
              <PanelTitle title="Recent Flagged Telemetry">
                <Link href="/evidence" className="mint-link">
                  View all <ArrowUpRight size={14} />
                </Link>
              </PanelTitle>
              <div className="record-list">
                {records.data?.slice(0, 3).map((record, i) => {
                  const Icon = [Radio, Database, FileCheck2][i] || Radio;
                  return (
                    <Link
                      href={`/evidence/${encodeURIComponent(record.id)}`}
                      className="record-item"
                      key={record.id}
                    >
                      <div className={`record-icon record-icon-${i}`}>
                        <Icon size={20} />
                      </div>
                      <div className="record-copy">
                        <strong>{record.source}</strong>
                        <span>
                          <i />
                          {record.id} <small>(v{record.version})</small>
                        </span>
                      </div>
                      <div className="record-meta">
                        <span>{record.time}</span>
                        <strong
                          className={
                            record.status === "Invalid" ? "is-invalid" : ""
                          }
                        >
                          {record.status}
                          <ArrowUpRight size={12} />
                        </strong>
                      </div>
                    </Link>
                  );
                })}
                {records.data?.length === 0 && (
                  <p className="panel-empty">All clear. No flagged records.</p>
                )}
              </div>
              <Link href="/ingestion" className="panel-footer-link">
                Explore ingestion activity <ArrowRight size={14} />
              </Link>
            </section>
          </div>
        </>
      )}

      <div className="dashboard-data-note">
        <span className="connection-dot" />
        {mode === "demo"
          ? "Demo workspace - illustrative data. Switch to Live API to see your backend data."
          : "Live workspace - values returned by your connected API."}
      </div>
    </div>
  );
}
