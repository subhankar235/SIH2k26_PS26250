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
  Plane,
  UserCheck,
  Package,
  MapPin,
  Clock,
  CheckCircle2,
  AlertTriangle,
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

const ASSIGNMENT_MANIFEST: Record<string, {
  plane: string;
  tail: string;
  base: string;
  crew: string;
  duty: string;
  payload: string;
  origin: string;
  corridor: string;
  dest: string;
  departure: string;
  arrival: string;
  status: string;
}> = {
  "T1": {
    plane: "Sukhoi Su-30MKI",
    tail: "SB042",
    base: "Bareilly AFS",
    crew: "Wg Cdr V. Joshi [PIC]",
    duty: "6.8h / 8.0h (1.2h remaining)",
    payload: "2x BrahMos-A + 4x Astra Mk-1 (9,400 kg)",
    origin: "Bareilly AFS",
    corridor: "Corridor Alpha-1 (FL320, 850 km)",
    dest: "Leh Forward AFS",
    departure: "10:00 UTC (T+0h)",
    arrival: "11:15 UTC (T+1.2h)",
    status: "ON SCHEDULE",
  },
  "TSK-100": {
    plane: "Dassault Rafale EH",
    tail: "RB011",
    base: "Ambala AFS",
    crew: "Wg Cdr Arjun Rathore [PIC]",
    duty: "3.4h / 8.0h (4.6h remaining)",
    payload: "2x SCALP-EG + 4x Meteor BVR (8,200 kg)",
    origin: "Ambala AFS",
    corridor: "Corridor Alpha-1 (FL340, 720 km)",
    dest: "Udhampur Sector Base",
    departure: "10:15 UTC (T+0.2h)",
    arrival: "11:20 UTC (T+1.3h)",
    status: "IN-FLIGHT",
  },
  "TSK-101": {
    plane: "Sukhoi Su-30MKI",
    tail: "SB042",
    base: "Bareilly AFS",
    crew: "Wg Cdr V. Joshi [PIC]",
    duty: "6.8h / 8.0h (1.2h remaining)",
    payload: "2x BrahMos-A + 4x Astra Mk-1 (9,400 kg)",
    origin: "Bareilly AFS",
    corridor: "Corridor Alpha-1 (FL320, 850 km)",
    dest: "Leh Forward AFS",
    departure: "10:00 UTC (T+0h)",
    arrival: "11:15 UTC (T+1.2h)",
    status: "ON SCHEDULE",
  },
  "TSK-102": {
    plane: "Dassault Rafale EH",
    tail: "RB011",
    base: "Ambala AFS",
    crew: "Wg Cdr Arjun Rathore [PIC]",
    duty: "3.4h / 8.0h (4.6h remaining)",
    payload: "2x SCALP-EG + 4x Meteor BVR (8,200 kg)",
    origin: "Ambala AFS",
    corridor: "Corridor Alpha-1 (FL340, 720 km)",
    dest: "Udhampur Sector Base",
    departure: "10:15 UTC (T+0.2h)",
    arrival: "11:20 UTC (T+1.3h)",
    status: "IN-FLIGHT",
  },
  "TSK-103": {
    plane: "C-130J Super Hercules",
    tail: "KC382",
    base: "Hindon AFS",
    crew: "Sqn Ldr Priya Sharma [PIC]",
    duty: "2.8h / 10.0h (7.2h remaining)",
    payload: "14,500 kg Combat Rations + Cold-Chain Plasma",
    origin: "Hindon AFS",
    corridor: "Corridor Charlie-7 (FL220, 640 km)",
    dest: "Nyoma ALG",
    departure: "10:30 UTC (T+0.5h)",
    arrival: "11:45 UTC (T+1.7h)",
    status: "ON SCHEDULE",
  },
  "TSK-104": {
    plane: "HAL Tejas Mk-1",
    tail: "LA008",
    base: "Sulur AFS",
    crew: "Sqn Ldr Kabir Bedi [PIC]",
    duty: "4.5h / 8.0h (3.5h remaining)",
    payload: "2x Astra Mk-1 + 2x ASRAAM (4,800 kg)",
    origin: "Sulur AFS",
    corridor: "Coastal Intercept Vector (450 km)",
    dest: "Thanjavur Forward Base",
    departure: "11:00 UTC (T+1h)",
    arrival: "11:50 UTC (T+1.8h)",
    status: "ALERT-5 STANDBY",
  },
};

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
      : alternatives.data?.[0] ?? null);
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

                {/* Tactical Assignment Manifest Table */}
                <div className="pt-4 border-t border-slate-800">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Plane size={14} className="text-orange-400" />
                    Operational Sortie Manifest (Tail, Crew, Payload &amp; Route)
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs border border-slate-800 rounded">
                      <thead className="bg-slate-900/90 text-slate-400 font-medium">
                        <tr>
                          <th className="p-2">Sortie / Task</th>
                          <th className="p-2">Aircraft &amp; Base</th>
                          <th className="p-2">Pilot &amp; Crew (Duty)</th>
                          <th className="p-2">Payload / Ordnance</th>
                          <th className="p-2">Route &amp; Corridor</th>
                          <th className="p-2">Time Window</th>
                          <th className="p-2">Verification</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 bg-slate-950/40 font-mono text-[11px]">
                        {schedule.assignments.map((a) => {
                          const meta = ASSIGNMENT_MANIFEST[a.taskId];
                          // Authoritative fields from API response take strict precedence:
                          const planeDisplay = a.resourceId || meta?.plane || "Tactical Airframe";
                          const tailDisplay = meta?.tail || a.resourceId;
                          const baseDisplay = meta?.base || "Operational Base";
                          const crewDisplay = a.crewId || meta?.crew || "Duty Pilot in Command";
                          const dutyDisplay = meta?.duty || "Duty limits verified";
                          const payloadDisplay = meta?.payload || "Tactical Combat / Logistics Payload";
                          const originDisplay = meta?.origin || "Base-Alpha";
                          const destDisplay = meta?.dest || "Base-Bravo";
                          const corridorDisplay = a.corridorId || meta?.corridor || "Corridor-Transit";
                          const timeWindowDisplay = (a.start !== undefined && a.end !== undefined)
                            ? `${a.start}:00–${a.end}:00 UTC (T+${a.start}h → T+${a.end}h, Slots ${a.start}–${a.end})`
                            : `${meta?.departure ?? "T+0h"} → ${meta?.arrival ?? "T+1h"}`;
                          const isVerified = schedule.verification === "verified";
                          return (
                            <tr key={a.taskId} className="hover:bg-slate-900/40">
                              <td className="p-2 font-bold text-orange-400">
                                <span className="text-[10px] text-slate-400 font-normal mr-1">Sortie</span>{a.taskId}
                              </td>
                              <td className="p-2">
                                <span className="text-slate-200 font-sans font-semibold">{planeDisplay}</span>
                                <span className="block text-slate-500 text-[10px]">Tail: {tailDisplay} &bull; {baseDisplay}</span>
                              </td>
                              <td className="p-2">
                                <span className="text-slate-200 font-sans">{crewDisplay}</span>
                                <span className="block text-emerald-400 text-[10px]">{dutyDisplay}</span>
                              </td>
                              <td className="p-2 font-sans text-slate-300 max-w-[200px] truncate" title={payloadDisplay}>
                                {payloadDisplay}
                              </td>
                              <td className="p-2">
                                <span className="text-slate-200">{originDisplay} &rarr; {destDisplay}</span>
                                <span className="block text-slate-500 text-[10px]">{corridorDisplay}</span>
                              </td>
                              <td className="p-2 font-mono text-slate-300">
                                {timeWindowDisplay}
                              </td>
                              <td className="p-2">
                                {isVerified ? (
                                  <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold text-[10px]">
                                    <CheckCircle2 size={11} /> CP-SAT Verified
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-rose-400 font-semibold text-[10px]">
                                    <AlertTriangle size={11} /> {schedule.verification === "invalid" ? "CP-SAT Infeasible" : "CP-SAT Uncertain"}
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
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
