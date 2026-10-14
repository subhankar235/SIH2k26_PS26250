"use client";
import React, { useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout";
import { Card, CardHeader, CardContent, Button, Badge } from "@/components/ui";
import { ScheduleGantt } from "@/components/charts";
import { VerificationBadge } from "@/components/validity/VerificationBadge";
import {
  SlidersHorizontal,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { solveSchedule, getAlternatives } from "@/lib/api/planning";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useDataMode } from "@/lib/data-mode";
import { Schedule } from "@/types/schedule";

export default function PlanningPage() {
  const [capacity, setCapacity] = useState<number>(4);
  const [horizon, setHorizon] = useState<number>(8);
  const { mode } = useDataMode();
  const [solvedSchedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<Error | string | null>(null);
  const alternatives = useFetch(getAlternatives);
  const schedule =
    solvedSchedule ??
    (mode === "demo"
      ? alternatives.data?.find((s) => s.id === "SCH-842")
      : null);
  const [objective, setObjective] = useState("utilization");
  const handleSolve = async () => {
    setLoading(true);
    setError(null);
    try {
      setSchedule(await solveSchedule(capacity, horizon));
      await alternatives.refetch();
    } catch (err) {
      setError(err instanceof Error ? err : "Solve failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F5"
        title="Schedule Optimization & Resource Allocation"
        description="Deterministic CP-SAT solver and longest-task-first heuristics allocate mission tasks across constrained resource units."
        actions={
          <Link href="/planning/compare">
            <span className="inline-flex items-center rounded border border-slate-700 px-3 py-2 text-xs text-sky-300 hover:bg-slate-800">
              Compare Replan Diff (F6) <ArrowRight size={14} className="ml-1" />
            </span>
          </Link>
        }
      />

      <LoadState loading={false} error={error} action />
      {/* Solver Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader
            title="Solver Parameters"
            subtitle="Specify operational bounds"
          />
          <CardContent className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Resource Capacity:{" "}
                <span className="font-mono text-sky-400 font-bold">
                  {capacity} units
                </span>
              </label>
              <input
                aria-label="Resource capacity"
                type="range"
                min={1}
                max={6}
                value={capacity}
                onChange={(e) => setCapacity(parseInt(e.target.value))}
                className="w-full accent-sky-500"
              />
              <span className="text-[10px] text-slate-500">
                Try capacity 1 and horizon 4 to trigger infeasibility.
              </span>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Time Horizon:{" "}
                <span className="font-mono text-sky-400 font-bold">
                  {horizon} hours
                </span>
              </label>
              <input
                aria-label="Time horizon"
                type="range"
                min={4}
                max={12}
                value={horizon}
                onChange={(e) => setHorizon(parseInt(e.target.value))}
                className="w-full accent-sky-500"
              />
            </div>

            <Button
              variant="primary"
              size="md"
              loading={loading}
              onClick={handleSolve}
              className="w-full"
            >
              <SlidersHorizontal size={14} className="mr-1.5" /> Run
              Optimisation
            </Button>
          </CardContent>
        </Card>

        {/* Schedule Result / Status */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Active Schedule Output"
            subtitle={
              schedule
                ? `Plan ID: ${schedule.id} · Version ${schedule.version}`
                : "Configure and run solve request"
            }
            action={
              schedule && <VerificationBadge status={schedule.verification} />
            }
          />
          <CardContent>
            {!schedule ? (
              <div className="p-8 text-center text-xs text-slate-400">
                Click <strong>Run Optimisation</strong> to generate candidate
                schedule assignments.
              </div>
            ) : schedule.verification === "invalid" ? (
              <div className="p-6 bg-rose-950/30 border border-rose-900/60 rounded text-center text-xs text-rose-300 space-y-2">
                <p className="font-semibold text-sm">
                  Schedule Verification Failed
                </p>
                <p>
                  The schedule failed verification. Review its constraints
                  before using it.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <ScheduleGantt
                  assignments={schedule.assignments}
                  horizon={horizon}
                />
                <div className="grid grid-cols-3 gap-2 text-center text-xs pt-2">
                  <div className="p-2 bg-slate-950 rounded border border-slate-800">
                    <span className="text-slate-400">Utilization:</span>
                    <p className="font-mono font-bold text-slate-200">
                      {schedule.objectives.utilization}%
                    </p>
                  </div>
                  <div className="p-2 bg-slate-950 rounded border border-slate-800">
                    <span className="text-slate-400">Assignments:</span>
                    <p className="font-mono font-bold text-slate-200">
                      {schedule.assignments.length}
                    </p>
                  </div>
                  <div className="p-2 bg-slate-950 rounded border border-slate-800">
                    <span className="text-slate-400">Check Status:</span>
                    <p className="font-mono font-bold text-emerald-400">
                      {schedule.verification}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader title="Objective trade-offs across alternatives" />
        <CardContent>
          <LoadState
            {...alternatives}
            resource="Schedule alternatives"
            empty={alternatives.data?.length === 0}
          />
          {!!alternatives.data?.length && (
            <>
              <label className="text-sm">
                Objective{" "}
                <select
                  className="bg-slate-900 p-2"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                >
                  {Array.from(
                    new Set([
                      "utilization",
                      ...alternatives.data.flatMap((a) =>
                        Object.keys(a.objectives),
                      ),
                    ]),
                  ).map((key) => (
                    <option key={key}>{key}</option>
                  ))}
                </select>
              </label>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={alternatives.data.map((a) => ({
                      id: a.id,
                      value: a.objectives[objective],
                    }))}
                  >
                    <XAxis dataKey="id" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="value" fill="#38bdf8" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="space-y-2">
                {alternatives.data.map((a) => (
                  <li key={a.id} className="flex gap-3">
                    <span>{a.id}</span>
                    <VerificationBadge status={a.verification} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
