import React from 'react';
import { Card, CardHeader, CardContent } from '@/components/ui';

export function DependencyGraphView({ title = "Input-to-Decision Dependencies" }: { title?: string }) {
  return (
    <Card>
      <CardHeader title={title} subtitle="Dependency chain indicating version impact on validity" />
      <CardContent>
        <div className="p-4 bg-slate-950/60 rounded border border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4 text-xs font-mono">
          <div className="p-3 bg-slate-900 border border-slate-700 rounded text-center w-full md:w-44">
            <p className="text-slate-400 text-[10px]">INPUT SOURCE</p>
            <p className="text-sky-300 font-semibold mt-0.5">REC-1049 (v1)</p>
            <span className="text-[10px] text-emerald-400">Schema Validated</span>
          </div>
          <div className="text-slate-600 font-bold text-base hidden md:block">→</div>
          <div className="p-3 bg-slate-900 border border-slate-700 rounded text-center w-full md:w-44">
            <p className="text-slate-400 text-[10px]">VERIFIER RULE</p>
            <p className="text-amber-300 font-semibold mt-0.5">Constraint 4-Check</p>
            <span className="text-[10px] text-slate-400">Deterministic Heuristic</span>
          </div>
          <div className="text-slate-600 font-bold text-base hidden md:block">→</div>
          <div className="p-3 bg-slate-900 border border-slate-700 rounded text-center w-full md:w-44">
            <p className="text-slate-400 text-[10px]">TARGET DECISION</p>
            <p className="text-emerald-300 font-semibold mt-0.5">SCH-842 (Dispatch)</p>
            <span className="text-[10px] text-emerald-400">Status: Verified</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
