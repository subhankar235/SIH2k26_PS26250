import React from 'react';
import { Card, CardHeader, CardContent } from '@/components/ui';

export function EvidenceGraph({ label = "RESOURCE-008" }: { label?: string }) {
  return (
    <Card>
      <CardHeader title="Evidence Relationships" subtitle={`Lineage and contradictions for ${label}`} />
      <CardContent>
        <div className="h-48 rounded bg-slate-950 border border-slate-800 p-4 flex flex-col justify-between text-xs">
          <div className="flex justify-between items-center text-slate-400">
            <span>[Source A: Registry]</span>
            <span className="text-rose-400 font-mono">--- Contradiction (Δ 4 units) ---</span>
            <span>[Source B: Telemetry]</span>
          </div>
          <div className="flex justify-center">
            <div className="p-2 border border-sky-600 bg-sky-950/40 rounded text-center">
              <span className="font-bold text-sky-300">{label}</span>
              <p className="text-[10px] text-slate-400">Target Asset / Constraint Node</p>
            </div>
          </div>
          <div className="flex justify-center text-[11px] text-slate-500">
            Dependent Decision: SCH-024 (Stale pending resolution)
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
