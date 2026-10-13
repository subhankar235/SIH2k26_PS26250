'use client';
import React, { useState, useEffect } from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardHeader, CardContent, Button, Spinner, Badge } from '@/components/ui';
import { ValidityBadge } from '@/components/validity/ValidityBadge';
import { ApprovalPanel } from '@/components/approvals/ApprovalPanel';
import { getApprovals, submitDecision, ApprovalItem } from '@/lib/api/approvals';
import { ShieldCheck, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react';

export default function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeItem, setActiveItem] = useState<ApprovalItem | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getApprovals().then((data) => {
      setItems(data);
      setLoading(false);
    });
  }, []);

  const handleApprove = async (reviewer: string, reason: string) => {
    if (!activeItem) return;
    await submitDecision(activeItem.id, 'approved', reviewer, reason);
    setItems((prev) =>
      prev.map((it) => (it.id === activeItem.id ? { ...it, status: 'approved' } : it))
    );
    setMessage(`Successfully approved ${activeItem.targetId}. Recorded in audit log.`);
    setActiveItem(null);
  };

  const handleReject = async (reviewer: string, reason: string) => {
    if (!activeItem) return;
    await submitDecision(activeItem.id, 'rejected', reviewer, reason);
    setItems((prev) =>
      prev.map((it) => (it.id === activeItem.id ? { ...it, status: 'rejected' } : it))
    );
    setMessage(`Successfully rejected ${activeItem.targetId}. Review recorded.`);
    setActiveItem(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Human-in-the-Loop Approvals (F9)"
        description="Strict safety review queue for mission schedules, replanning proposals, and operational interventions"
        actions={
          <Badge variant="outline" className="border-emerald-800 text-emerald-300">
            <ShieldCheck size={12} className="mr-1 inline" /> Strict Verification Gate Active
          </Badge>
        }
      />

      {message && (
        <div className="p-3 bg-emerald-950/40 border border-emerald-800 text-xs text-emerald-300 rounded flex items-center justify-between">
          <span>{message}</span>
          <button onClick={() => setMessage(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Active Modal / Gate Drawer */}
      {activeItem && (
        <ApprovalPanel
          targetId={activeItem.targetId}
          title={`${activeItem.type}: ${activeItem.summary}`}
          verification={activeItem.verification}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}

      {/* Queue Table */}
      <Card className="border-slate-800">
        <CardHeader
          title="Review Queue"
          subtitle="Mandatory rule: Only verified items may be approved into execution"
        />
        <CardContent>
          {loading ? (
            <div className="py-12 flex justify-center"><Spinner /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 uppercase font-semibold">
                  <tr>
                    <th className="px-4 py-2.5">Approval ID</th>
                    <th className="px-4 py-2.5">Target</th>
                    <th className="px-4 py-2.5">Type</th>
                    <th className="px-4 py-2.5">Verification</th>
                    <th className="px-4 py-2.5">Submitted By</th>
                    <th className="px-4 py-2.5">Submitted At</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {items.map((it) => (
                    <tr key={it.id} className="hover:bg-slate-800/30">
                      <td className="px-4 py-3 font-semibold text-sky-400">{it.id}</td>
                      <td className="px-4 py-3 text-slate-200">{it.targetId}</td>
                      <td className="px-4 py-3 font-sans text-slate-300">{it.type}</td>
                      <td className="px-4 py-3">
                        <ValidityBadge status={it.verification} />
                      </td>
                      <td className="px-4 py-3 font-sans text-slate-400">{it.submittedBy}</td>
                      <td className="px-4 py-3 text-slate-400">{it.submittedAt}</td>
                      <td className="px-4 py-3">
                        <Badge
                          variant="outline"
                          className={
                            it.status === 'approved'
                              ? 'border-emerald-800 text-emerald-300'
                              : it.status === 'rejected'
                              ? 'border-rose-800 text-rose-300'
                              : 'border-amber-800 text-amber-300'
                          }
                        >
                          {it.status.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right font-sans">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setActiveItem(it)}
                          className="bg-slate-800 hover:bg-slate-700 text-slate-200"
                        >
                          Review Gate
                        </Button>
                      </td>
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
