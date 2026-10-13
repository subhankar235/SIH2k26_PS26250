'use client';
import React, { useState } from 'react';
import { Card, CardHeader, CardContent, Button } from '@/components/ui';
import { ValidityBadge } from '@/components/validity/ValidityBadge';
import { ValidityStatus } from '@/types/validity';
import { ShieldCheck, AlertCircle } from 'lucide-react';

export function ApprovalPanel({
  targetId,
  title,
  verification,
  onApprove,
  onReject,
  loading,
}: {
  targetId: string;
  title: string;
  verification: ValidityStatus;
  onApprove: (reviewer: string, reason: string) => Promise<boolean | void>;
  onReject: (reviewer: string, reason: string) => Promise<boolean | void>;
  loading?: boolean;
}) {
  const [reviewer, setReviewer] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const isVerified = verification === 'verified';

  const handleApprove = async () => {
    if (!reviewer.trim() || !reason.trim()) {
      setError('Reviewer name and approval reason are mandatory.');
      return;
    }
    setError(null);
    await onApprove(reviewer, reason);
  };

  const handleReject = async () => {
    if (!reviewer.trim() || !reason.trim()) {
      setError('Reviewer name and rejection reason are mandatory.');
      return;
    }
    setError(null);
    await onReject(reviewer, reason);
  };

  return (
    <Card className="border-slate-700">
      <CardHeader
        title={`Review & Approval Gate: ${targetId}`}
        subtitle={title}
        action={<ValidityBadge status={verification} />}
      />
      <CardContent className="space-y-4">
        {!isVerified && (
          <div className="p-3 bg-rose-950/40 border border-rose-900/60 rounded flex items-center gap-2.5 text-xs text-rose-300">
            <AlertCircle size={16} className="text-rose-400 flex-shrink-0" />
            <span>Strict Rule: Only results with <strong>verified</strong> status can be approved. Resolve validation checks first.</span>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">Reviewer Name / ID</label>
            <input
              type="text"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              placeholder="e.g., Staff Analyst KD"
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">Decision Rationale</label>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="State reasons for approval or rejection based on evidence..."
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>

          {error && <p className="text-xs text-rose-400">{error}</p>}

          <div className="flex gap-2 justify-end pt-2">
            <Button
              variant="danger"
              size="sm"
              loading={loading}
              onClick={handleReject}
            >
              Reject Result
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!isVerified}
              loading={loading}
              onClick={handleApprove}
            >
              <ShieldCheck size={14} className="mr-1" />
              Approve Result
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
