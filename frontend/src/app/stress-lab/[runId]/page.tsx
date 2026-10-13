'use client';
import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader, CardContent, Button, Spinner, Badge } from '@/components/ui';
import { MetricBarChart } from '@/components/charts/MetricBarChart';
import { getStressRunById } from '@/lib/api/stress';
import { StressRun } from '@/types/stress';
import { ArrowLeft, CheckCircle2, ShieldCheck, Zap, AlertTriangle } from 'lucide-react';

export default function StressRunDetailPage() {
  const params = useParams();
  const runId = (params?.runId as string) || 'RUN-42';
  const [run, setRun] = useState<StressRun | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStressRunById(runId).then((data) => {
      setRun(data);
      setLoading(false);
    });
  }, [runId]);

  if (loading) {
    return (
      <div className="py-20 flex justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="p-8 text-center text-slate-400">
        <p>Stress test run {runId} not found.</p>
        <Link href="/stress-lab" className="text-sky-400 underline mt-2 inline-block">Return to Stress Lab</Link>
      </div>
    );
  }

  const comparisonData = [
    { metric: 'Detection Rate (%)', system: run.detectionRate, baseline: 74.2 },
    { metric: 'Recovery Time (s)', system: run.recoveryTime, baseline: run.baseline },
    { metric: 'Feasibility (%)', system: run.feasibility, baseline: 83.1 },
    { metric: 'False Alarms', system: run.falseAlarms, baseline: 8.5 },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link href="/stress-lab" className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1">
          <ArrowLeft size={14} /> Back to Stress Testing Lab
        </Link>
      </div>

      <PageHeader
        title={`Stress Run Autopsy: ${run.id}`}
        description={`Detailed breakdown of fault injection, automated recovery, and baseline divergence`}
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-emerald-800 text-emerald-300">
              <CheckCircle2 size={12} className="mr-1 inline" /> {run.status.toUpperCase()}
            </Badge>
          </div>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-slate-800">
          <CardContent className="pt-4">
            <div className="text-xs text-slate-400">Fault Detection</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{run.detectionRate}%</div>
            <div className="text-[10px] text-slate-500 mt-0.5">+24.2% over baseline</div>
          </CardContent>
        </Card>
        <Card className="border-slate-800">
          <CardContent className="pt-4">
            <div className="text-xs text-slate-400">Recovery Time</div>
            <div className="text-2xl font-bold text-sky-400 mt-1">{run.recoveryTime}s</div>
            <div className="text-[10px] text-slate-500 mt-0.5">vs {run.baseline}s baseline</div>
          </CardContent>
        </Card>
        <Card className="border-slate-800">
          <CardContent className="pt-4">
            <div className="text-xs text-slate-400">Schedule Feasibility</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{run.feasibility}%</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Under {run.faultSeverity} fault load</div>
          </CardContent>
        </Card>
        <Card className="border-slate-800">
          <CardContent className="pt-4">
            <div className="text-xs text-slate-400">False Alarms</div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{run.falseAlarms}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Down from 8.5 baseline</div>
          </CardContent>
        </Card>
      </div>

      {/* Comparison Chart */}
      <Card className="border-slate-800">
        <CardHeader
          title="Empirical Performance vs Baseline Heuristic"
          subtitle="Direct comparison under identical perturbation seed"
        />
        <CardContent>
          <MetricBarChart data={comparisonData} />
        </CardContent>
      </Card>

      {/* Injected Fault Sequence */}
      <Card className="border-slate-800">
        <CardHeader
          title="Injected Chaos Trace & Self-Healing Actions"
          subtitle="Step-by-step resolution of induced anomalies"
        />
        <CardContent>
          <div className="space-y-4">
            <div className="p-3 rounded border border-slate-800 bg-slate-900/40 flex items-start gap-3">
              <Zap size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs font-semibold text-slate-200">Fault 1: Telemetry Stream Latency (320ms drift)</div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Artificially delayed incoming telemetry packets for topic sensors.environmental. TGN temporal tracker flagged stale input.
                </p>
              </div>
            </div>

            <div className="p-3 rounded border border-slate-800 bg-slate-900/40 flex items-start gap-3">
              <AlertTriangle size={16} className="text-rose-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs font-semibold text-slate-200">Fault 2: Resource 008 Contradiction</div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Registry claimed available status while telemetry reported active maintenance. Ditto entity resolution reconciled disagreement.
                </p>
              </div>
            </div>

            <div className="p-3 rounded border border-emerald-900/40 bg-emerald-950/20 flex items-start gap-3">
              <ShieldCheck size={16} className="text-emerald-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-xs font-semibold text-emerald-300">Self-Correction: CP-SAT Minimal Perturbation Replan</div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Generated non-disruptive schedule diff with 0 task cancellations and 1 task reassignment, completing recovery in {run.recoveryTime}s.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
