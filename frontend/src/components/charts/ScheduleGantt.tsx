'use client';
import React from 'react';
import { Assignment } from '@/types/schedule';

export function ScheduleGantt({ assignments, horizon = 8 }: { assignments: Assignment[]; horizon?: number }) {
  const resources = Array.from(new Set(assignments.map(a => a.resourceId))).sort();

  return (
    <div className="w-full overflow-x-auto p-4 bg-slate-950/80 rounded border border-slate-800">
      {/* Time axis header */}
      <div className="grid grid-cols-9 gap-1 text-[11px] font-mono text-slate-500 pb-2 border-b border-slate-800">
        <div className="font-semibold text-slate-400">Resource</div>
        {Array.from({ length: horizon }).map((_, h) => (
          <div key={h} className="text-center">T+{h}h</div>
        ))}
      </div>

      {/* Resource timeline rows */}
      <div className="space-y-3 pt-3">
        {resources.map((res) => {
          const resTasks = assignments.filter(a => a.resourceId === res);
          return (
            <div key={res} className="grid grid-cols-9 gap-1 items-center">
              <div className="text-xs font-mono font-medium text-slate-300">{res}</div>
              <div className="col-span-8 relative h-7 bg-slate-900/60 rounded border border-slate-800/80">
                {resTasks.map((task) => {
                  const leftPct = (task.start / horizon) * 100;
                  const widthPct = ((task.end - task.start) / horizon) * 100;
                  return (
                    <div
                      key={task.taskId}
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                      className="absolute top-1 bottom-1 bg-sky-600/80 hover:bg-sky-500 border border-sky-400/50 rounded flex items-center justify-center text-[10px] font-mono text-white transition-colors"
                      title={`${task.taskId}: ${task.start}h → ${task.end}h`}
                    >
                      {task.taskId}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
