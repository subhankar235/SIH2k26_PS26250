'use client';
import React, { use, useState } from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Button } from '@/components/ui';
import { ValidityBadge, DependencyGraphView } from '@/components/validity';
import { ArrowLeft, RefreshCw, CheckCircle2 } from 'lucide-react';
import { MOCK_DECISIONS } from '@/lib/fixtures';
import { reverifyDecision } from '@/lib/api/validity';

export default function ValidityDetailPage({ params }: { params: Promise<{ decisionId: string }> }) {
  const { decisionId } = use(params);
  const decision = MOCK_DECISIONS.find(d => d.id === decisionId) || MOCK_DECISIONS[0];
  const [status, setStatus] = useState(decision.status);
  const [loading, setLoading] = useState(false);

  const handleReverify = async () => {
    setLoading(true);
    await reverifyDecision(decisionId);
    setStatus('verified');
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xs">
        <Link href="/validity" className="text-slate-400 hover:text-slate-200 flex items-center gap-1">
          <ArrowLeft size={14} /> Back to Decisions
        </Link>
      </div>

      <PageHeader
        eyebrow="VALIDITY INSPECTOR"
        title={`Decision Detail: ${decisionId}`}
        description="Assumptions, input versions, dependency graphs, and status transition history."
        actions={
          <Button size="sm" variant="primary" loading={loading} onClick={handleReverify}>
            <RefreshCw size={14} className="mr-1.5" /> Re-Verify
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-1">
          <CardHeader title="Current State" subtitle="Recorded validity status" />
          <CardContent className="space-y-4 text-xs">
            <div>
              <span className="text-slate-400">Status:</span>
              <div className="mt-1"><ValidityBadge status={status} /></div>
            </div>
            <div>
              <span className="text-slate-400">Decision Type:</span>
              <p className="font-medium text-slate-200 mt-0.5">{decision.type} (v{decision.version})</p>
            </div>
            <div>
              <span className="text-slate-400">Timestamp:</span>
              <p className="font-mono text-slate-300 mt-0.5">{decision.createdAt}</p>
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader title="Underlying Assumptions" subtitle="Conditions verified at generation time" />
          <CardContent>
            <ul className="space-y-2 text-xs">
              {decision.assumptions.map(a => (
                <li key={a.id} className="p-2.5 bg-slate-950/60 rounded border border-slate-800 flex items-center gap-2">
                  <CheckCircle2 size={14} className="text-emerald-400" />
                  <span className="font-mono text-slate-400">[{a.id}]</span>
                  <span className="text-slate-200">{a.description}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <DependencyGraphView title="Input Dependency Graph" />
    </div>
  );
}
