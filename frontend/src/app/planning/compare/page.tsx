'use client';
import React from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import { ScheduleDiffView } from '@/components/planning';
import { ArrowLeft } from 'lucide-react';
import { useFetch } from '@/hooks/useFetch';
import { getScheduleDiff } from '@/lib/api/planning';

export default function PlanningComparePage() {
  const { data: diff, loading } = useFetch(() => getScheduleDiff('SCH-841', 'SCH-842'));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xs">
        <Link href="/planning" className="text-slate-400 hover:text-slate-200 flex items-center gap-1">
          <ArrowLeft size={14} /> Back to Planning
        </Link>
      </div>

      <PageHeader
        eyebrow="FEATURE F6"
        title="Schedule Diff & Replanning Autopsy"
        description="Inspect minimal disruption replanning outcomes: added, removed, moved, and unchanged assignments."
      />

      {loading || !diff ? (
        <p className="text-xs text-slate-400">Calculating schedule diff...</p>
      ) : (
        <ScheduleDiffView diff={diff} />
      )}
    </div>
  );
}
