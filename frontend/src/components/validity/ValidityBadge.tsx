import React from 'react';
import { ValidityStatus } from '@/types/validity';
import { cn } from '@/lib/utils';

const STYLES: Record<ValidityStatus, string> = {
  verified: "bg-emerald-950 text-emerald-300 border border-emerald-800/60",
  stale: "bg-amber-950 text-amber-300 border border-amber-800/60",
  invalidated: "bg-rose-950 text-rose-300 border border-rose-800/60",
  invalid: "bg-rose-950 text-rose-300 border border-rose-800/60",
  uncertain: "bg-slate-800 text-slate-300 border border-slate-700/60",
};

export function ValidityBadge({ status, className }: { status: ValidityStatus; className?: string }) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 text-xs font-medium rounded uppercase tracking-wider font-mono", STYLES[status], className)}>
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5" />
      {status}
    </span>
  );
}
