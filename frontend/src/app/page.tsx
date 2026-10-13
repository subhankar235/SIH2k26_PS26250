'use client';
import React from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Button, Badge } from '@/components/ui';
import { ValidityBadge } from '@/components/validity/ValidityBadge';
import {
  ShieldCheck,
  AlertTriangle,
  Database,
  SlidersHorizontal,
  ArrowUpRight,
  Activity,
  CheckCircle2,
} from 'lucide-react';
import { MOCK_RECORDS, MOCK_DECISIONS } from '@/lib/fixtures';

export default function OverviewPage() {
  const verifiedCount = MOCK_DECISIONS.filter(d => d.status === 'verified').length + 20;
  const staleCount = MOCK_DECISIONS.filter(d => d.status === 'stale').length + 2;
  const invalidatedCount = MOCK_DECISIONS.filter(d => d.status === 'invalidated').length;
  const uncertainCount = MOCK_DECISIONS.filter(d => d.status === 'uncertain').length + 3;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="COMMAND CENTER"
        title="Grid Overview & Operational Readiness"
        description="Real-time situational intelligence, automated validity monitoring, and high-consequence decision gates."
        actions={
          <div className="flex gap-2">
            <Link href="/planning">
              <Button size="sm" variant="primary">
                <SlidersHorizontal size={14} className="mr-1.5" /> Open Planning
              </Button>
            </Link>
          </div>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex justify-between items-start text-xs text-slate-400">
              <span>Data Quality Score</span>
              <Activity size={14} className="text-emerald-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-slate-100 mt-2">96.8%</div>
            <p className="text-[11px] text-emerald-400 mt-1">↗ +2.4% vs baseline fixture</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex justify-between items-start text-xs text-slate-400">
              <span>Verified Outputs</span>
              <ShieldCheck size={14} className="text-emerald-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-emerald-300 mt-2">{verifiedCount}</div>
            <p className="text-[11px] text-slate-400 mt-1">Across 4 synthetic scenarios</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex justify-between items-start text-xs text-slate-400">
              <span>Open Conflicts (F2)</span>
              <AlertTriangle size={14} className="text-amber-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-amber-300 mt-2">07</div>
            <p className="text-[11px] text-amber-400/80 mt-1">3 require analyst review</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex justify-between items-start text-xs text-slate-400">
              <span>Pending Approvals (F9)</span>
              <CheckCircle2 size={14} className="text-sky-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-sky-300 mt-2">02</div>
            <p className="text-[11px] text-slate-400 mt-1">Human-in-the-loop gate</p>
          </CardContent>
        </Card>
      </div>

      {/* Middle Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Decision Readiness Donut/Summary */}
        <Card className="lg:col-span-1">
          <CardHeader title="Decision Readiness" subtitle="Distribution of output validity status" />
          <CardContent className="flex flex-col items-center justify-center p-6 space-y-4">
            <div className="w-36 h-36 rounded-full border-8 border-slate-800 relative flex items-center justify-center">
              <div className="text-center">
                <span className="text-3xl font-bold font-mono text-slate-100">32</span>
                <p className="text-[10px] text-slate-400 uppercase tracking-wider">Total Decisions</p>
              </div>
            </div>
            <div className="w-full space-y-2 pt-2 text-xs">
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-emerald-400" /> Verified</span>
                <span className="font-mono font-semibold text-slate-200">{verifiedCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> Stale (Inputs Changed)</span>
                <span className="font-mono font-semibold text-slate-200">{staleCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-rose-400" /> Invalidated</span>
                <span className="font-mono font-semibold text-slate-200">{invalidatedCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-slate-400" /> Uncertain</span>
                <span className="font-mono font-semibold text-slate-200">{uncertainCount}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Flagged Records & Critical Attention */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Telemetry & Ingestion Events"
            subtitle="Flagged records from active streaming topics"
            action={<Link href="/ingestion" className="text-xs text-sky-400 hover:underline">View All Ingestion →</Link>}
          />
          <CardContent className="p-0">
            <div className="divide-y divide-slate-800">
              {MOCK_RECORDS.slice(0, 4).map((rec) => (
                <div key={rec.id} className="p-4 flex items-center justify-between text-xs hover:bg-slate-800/20">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-slate-200">{rec.id}</span>
                      <Badge tone={rec.status === 'Valid' ? 'green' : rec.status === 'Invalid' ? 'red' : 'amber'}>
                        {rec.status}
                      </Badge>
                      {rec.duplicate && <Badge tone="gray">Duplicate</Badge>}
                    </div>
                    <p className="text-[11px] text-slate-400">Source: {rec.source} · {rec.reason}</p>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-slate-400">{rec.time}</span>
                    <Link href={`/evidence/ISSUE-01`} className="block text-sky-400 hover:underline text-[11px] mt-0.5">
                      Inspect →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
