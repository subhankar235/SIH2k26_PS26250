import React from 'react';
import { Clock } from 'lucide-react';

export function ProvenanceTimeline({ steps }: { steps: { step: string; at: string; sourceId: string }[] }) {
  return (
    <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
      {steps.map((st, i) => (
        <div key={i} className="relative group">
          <div className="absolute -left-6 top-1 w-4 h-4 rounded-full bg-slate-900 border-2 border-sky-500 flex items-center justify-center">
            <div className="w-1.5 h-1.5 bg-sky-400 rounded-full" />
          </div>
          <div className="text-xs">
            <div className="flex items-center gap-2 text-slate-400">
              <span className="font-semibold text-slate-200">{st.step}</span>
              <span>·</span>
              <span className="flex items-center gap-1 font-mono text-[10px]"><Clock size={11} /> {st.at}</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">Source: {st.sourceId}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
