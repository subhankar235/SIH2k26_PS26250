"use client";
import { useState } from "react";
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
import { useDataMode } from "@/lib/data-mode";

const STATUS = [
  { key: "verified", label: "Verified", color: "#285b51" },
  { key: "stale", label: "Stale", color: "#82e2b6" },
  { key: "uncertain", label: "Uncertain", color: "#dcefe3" },
  { key: "invalidated", label: "Invalidated", color: "#dedee0" },
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
          stroke="#f0f3f1"
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
        const active = (i / 44) * 100 <= percent;
        return (
          <line
            key={i}
            x1={140 + 90 * Math.cos(angle)}
            y1={142 + 90 * Math.sin(angle)}
            x2={140 + 125 * Math.cos(angle)}
            y2={142 + 125 * Math.sin(angle)}
            stroke={active ? (i < 16 ? "#285b51" : "#87e4b8") : "#e1ece5"}
            strokeWidth="7"
            strokeLinecap="round"
          />
        );
      })}
      <text x="140" y="126" textAnchor="middle" className="gauge-value">
        {percent}%
      </text>
      <text x="140" y="149" textAnchor="middle" className="gauge-caption">
        ready for review
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
    <div className="dashboard-panel-title">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
export default function OverviewPage() {
  const { mode, setMode } = useDataMode();
  const demo = mode === "demo";
  const setDemo = (value: boolean) => setMode(value ? "demo" : "live");
  const [window, setWindow] = useState("24");
  const decisions = useFetch(getDecisions);
  const records = useFetch(getFlaggedRecords);
  const approvals = useFetch(getApprovals);
  const streams = useFetch(getIngestionStatus);
  const forecast = useFetch(() => getForecast());
  const health = useFetch(getHealth);
  const total = decisions.data?.length ?? 0;
  const counts = STATUS.map(
    (status) =>
      decisions.data?.filter((item) => item.status === status.key).length ?? 0,
  );
  const percent = total ? Math.round((counts[0] / total) * 100) : 0;
  const pending =
    approvals.data?.filter((item) => item.status === "pending") ?? [];
  const sourceData = (streams.data ?? []).slice(0, 6);
  const throughput = sourceData.reduce(
    (sum, source) =>
      sum + (Number.parseFloat(source.rate.replaceAll(",", "")) || 0),
    0,
  );
  const maxRate = Math.max(
    1,
    ...sourceData.map(
      (source) => Number.parseFloat(source.rate.replaceAll(",", "")) || 0,
    ),
  );
  const chartData = (forecast.data?.points ?? []).slice(
    0,
    window === "12" ? 6 : 12,
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
  return (
    <div className="dashboard">
      <div className="dashboard-top-row">
        <section className="welcome-panel">
          <div className="welcome-copy">
            <h2>
              Welcome back, <br />
              Kathakali!
            </h2>
            <p>
              A clear view of your data, decisions, and everything that needs
              your attention.
            </p>
            <Link href="/benchmarks" className="forest-button">
              View performance report <ArrowUpRight size={16} />
            </Link>
          </div>
          <div className="summary-card">
            <div className="summary-label">
              Total decisions
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
            <small>across your workspace</small>
          </div>
          <div className="summary-card">
            <div className="summary-label">
              Flagged records
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
              <Activity size={11} /> Needs attention
            </span>
            <small>ready for investigation</small>
          </div>
          <div className="summary-card">
            <div className="summary-label">
              Pending approvals
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
                pending.filter((item) => item.verification === "verified")
                  .length
              }{" "}
              ready to review
            </span>
            <small>your next decisions</small>
          </div>
        </section>
        <section className="dashboard-panel distribution-panel">
          <PanelTitle title="Decision health">
            <select
              className="mint-select"
              aria-label="Dashboard data source"
              value={demo ? "demo" : "live"}
              onChange={(e) => setDemo(e.target.value === "demo")}
            >
              <option value="demo">Demo data</option>
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
          <div className="dashboard-middle-row">
            <section className="dashboard-panel source-panel">
              <PanelTitle title="Activity by source">
                <Link href="/ingestion" className="mint-link">
                  View streams <ArrowUpRight size={14} />
                </Link>
              </PanelTitle>
              <div className="panel-headline">
                <strong>
                  {number(throughput)}
                  <span>/s</span>
                </strong>
                <span>Total ingestion rate</span>
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
                        {throughput ? Math.round((rate / throughput) * 100) : 0}
                        %
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
                {!sourceData.length && (
                  <p className="panel-empty">
                    {streams.loading
                      ? "Loading streams..."
                      : "No stream activity available."}
                  </p>
                )}
              </div>
            </section>
            <section className="dashboard-panel performance-panel">
              <PanelTitle title="Forecast performance">
                <select
                  aria-label="Forecast time window"
                  className="mint-select"
                  value={window}
                  onChange={(e) => setWindow(e.target.value)}
                >
                  <option value="24">24 hours</option>
                  <option value="12">12 hours</option>
                </select>
              </PanelTitle>
              <div className="performance-chart">
                <ResponsiveContainer width="100%" height="100%">
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
                          stopColor="#badcca"
                          stopOpacity={0.65}
                        />
                        <stop
                          offset="100%"
                          stopColor="#edf6f0"
                          stopOpacity={0.05}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#f0f3f1" />
                    <XAxis
                      dataKey="t"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#8a918d", fontSize: 11 }}
                      dy={10}
                      minTickGap={15}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#8a918d", fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        border: "none",
                        borderRadius: 12,
                        boxShadow: "0 10px 30px #214f4420",
                        fontSize: 12,
                      }}
                    />
                    <Area
                      isAnimationActive={false}
                      type="linear"
                      dataKey="mean"
                      name="Mean forecast"
                      stroke="#2b6355"
                      strokeWidth={1.5}
                      fill="url(#dashboard-forecast)"
                    />
                    <Line
                      isAnimationActive={false}
                      type="linear"
                      dataKey="lower"
                      name="Lower bound"
                      stroke="#87e4b8"
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
          <div className="dashboard-bottom-row">
            <section className="dashboard-panel target-panel">
              <PanelTitle title="Operational readiness">
                <CircleHelp size={17} className="muted-icon" />
              </PanelTitle>
              <div className="readiness-headline">
                <strong>
                  <ArrowUpRight size={22} />
                  {percent}%
                </strong>
                <p>
                  Verified decisions,
                  <br />
                  ready for your next move.
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
                <Link href="/validity">
                  View decisions <ArrowRight size={14} />
                </Link>
              </div>
              <div className="backend-status">
                <span
                  className={`connection-dot ${health.error ? "offline" : ""}`}
                />
                <span>Backend health</span>
                <strong>
                  {demo
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
            <section className="dashboard-panel records-panel">
              <PanelTitle title="Recent flagged records">
                <Link href="/evidence" className="mint-link">
                  View all <ArrowUpRight size={14} />
                </Link>
              </PanelTitle>
              <div className="record-list">
                {records.data?.slice(0, 3).map((record, i) => {
                  const Icon = [Radio, Database, FileCheck2][i];
                  return (
                    <Link
                      href={`/evidence/${encodeURIComponent(record.id)}`}
                      className="record-item"
                      key={record.id}
                    >
                      <div className={`record-icon record-icon-${i}`}>
                        <Icon size={23} />
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
            <section className="dashboard-panel approval-panel">
              <PanelTitle title="Approval readiness">
                <Link aria-label="Open approvals" href="/approvals">
                  <ArrowUpRight size={18} />
                </Link>
              </PanelTitle>
              <Gauge
                percent={
                  pending.length
                    ? Math.round(
                        (pending.filter(
                          (item) => item.verification === "verified",
                        ).length /
                          pending.length) *
                          100,
                      )
                    : 0
                }
              />
              <div className="approval-caption">
                <span>
                  <strong>{pending.length}</strong> results awaiting review
                </span>
                <Link href="/approvals">
                  Review queue <ArrowRight size={14} />
                </Link>
              </div>
            </section>
          </div>
        </>
      )}
      <div className="dashboard-data-note">
        <span className="connection-dot" />
        {demo
          ? "Demo workspace - illustrative data. Switch to Live API to see your backend data."
          : "Live workspace - values returned by your connected API."}
      </div>
    </div>
  );
}
