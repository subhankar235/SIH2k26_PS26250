import React from 'react';
import { Box } from 'lucide-react';
import { cn } from '@/lib/utils';

export function EmptyState({ icon: Icon = Box, title, message, action, className }: { icon?: React.ElementType; title: string; message: string; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("p-8 border border-dashed border-slate-800 rounded-lg text-center flex flex-col items-center justify-center space-y-3", className)}>
      <div className="p-3 bg-slate-800/40 rounded-full text-slate-400">
        <Icon size={28} />
      </div>
      <div>
        <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
        <p className="text-xs text-slate-400 mt-1 max-w-sm">{message}</p>
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
