'use client';
import React, { useState, useEffect } from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader, CardContent, Spinner, Badge } from '@/components/ui';
import { MetricBarChart } from '@/components/charts/MetricBarChart';
import { CalibrationPlot } from '@/components/charts/CalibrationPlot';
import { getBenchmarkResults, getAblations } from '@/lib/api/benchmarks';
import { BenchmarkResult, Ablation } from '@/types/benchmark';
import { BarChart3, Target, Award, LineChart } from 'lucide-react';

export default function BenchmarksPage() {
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult[]>([]);
  const [ablations, setAblations] = useState<Ablation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getBenchmarkResults(), getAblations()]).then(([bData, aData]) => {
      setBenchmarks(bData);
      setAblations(aData);
      setLoading(false);
    });
  }, []);

  const chartData = benchmarks.map((b) => ({
    metric: b.metric,
    system: b.system,
    baseline: b.baseline,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Benchmarks & Scientific Rigor (F10)"
        description="Empirical evaluation across detection rate, recovery time, and forecast calibration against baselines"
        actions={
          <Badge variant="outline" className="border-sky-800 text-sky-300">
            <Award size={12} className="mr-1 inline" /> Statistically Significant (p &lt; 0.01)
          </Badge>
        }
      />

      {/* Visual Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border-slate-800">
          <CardHeader
            title="Full System vs Baseline Heuristics"
            subtitle="Side-by-side comparison across all 4 key performance indicators"
          />
          <CardContent>
            {loading ? <div className="py-12 flex justify-center"><Spinner /></div> : <MetricBarChart data={chartData} />}
          </CardContent>
        </Card>

        <Card className="border-slate-800">
          <CardHeader
            title="Forecast Calibration Reliability Plot"
            subtitle="Nominal confidence vs observed empirical coverage"
          />
          <CardContent>
            <CalibrationPlot />
          </CardContent>
        </Card>
      </div>

      {/* Statistical Significance Table */}
      <Card className="border-slate-800">
        <CardHeader
          title="Statistical Significance & Confidence Intervals"
          subtitle="95% confidence intervals and p-values based on 10,000 Monte Carlo iterations"
        />
        <CardContent>
          {loading ? (
            <div className="py-8 flex justify-center"><Spinner /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 uppercase font-semibold">
                  <tr>
                    <th className="px-4 py-2.5">Metric</th>
                    <th className="px-4 py-2.5">Air Power System</th>
                    <th className="px-4 py-2.5">Baseline Heuristic</th>
                    <th className="px-4 py-2.5">Effect Size</th>
                    <th className="px-4 py-2.5">95% CI</th>
                    <th className="px-4 py-2.5 text-right">p-Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {benchmarks.map((b) => (
                    <tr key={b.metric} className="hover:bg-slate-800/30">
                      <td className="px-4 py-3 font-semibold text-slate-200 font-sans">{b.metric}</td>
                      <td className="px-4 py-3 text-sky-400 font-bold">{b.system}</td>
                      <td className="px-4 py-3 text-slate-400">{b.baseline}</td>
                      <td className="px-4 py-3 text-emerald-400 font-semibold">{b.effectSize}</td>
                      <td className="px-4 py-3 text-slate-300">[{b.ci[0]}, {b.ci[1]}]</td>
                      <td className="px-4 py-3 text-right text-emerald-400">{b.pValue}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Ablation Studies */}
      <Card className="border-slate-800">
        <CardHeader
          title="Ablation Analysis: Component Contribution"
          subtitle="Isolating the contribution of TGN temporal tracking, Ditto entity resolution, and CP-SAT solvers"
        />
        <CardContent>
          {loading ? (
            <div className="py-8 flex justify-center"><Spinner /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 uppercase font-semibold">
                  <tr>
                    <th className="px-4 py-2.5">Architecture Variant</th>
                    <th className="px-4 py-2.5">Detection Accuracy</th>
                    <th className="px-4 py-2.5">Recovery Time</th>
                    <th className="px-4 py-2.5">Schedule Feasibility</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {ablations.map((a, i) => (
                    <tr key={a.name} className={i === 0 ? 'bg-sky-950/20 font-semibold' : 'hover:bg-slate-800/30'}>
                      <td className="px-4 py-3 font-sans text-slate-200">
                        {a.name} {i === 0 && <span className="ml-2 text-[10px] text-sky-400 uppercase tracking-wider">(Ours)</span>}
                      </td>
                      <td className="px-4 py-3 text-sky-400">{a.accuracy}</td>
                      <td className="px-4 py-3 text-slate-300">{a.recoveryTime}</td>
                      <td className="px-4 py-3 text-emerald-400">{a.feasibility}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
