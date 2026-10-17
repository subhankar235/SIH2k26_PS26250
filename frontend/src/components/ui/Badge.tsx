import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeTone = 'green' | 'amber' | 'red' | 'blue' | 'violet' | 'gray';

const STYLES: Record<BadgeTone, string> = {
  green: 'bg-emerald-950 text-emerald-300 border-emerald-800/60',
  amber: 'bg-amber-950 text-amber-300 border-amber-800/60',
  red: 'bg-rose-950 text-rose-300 border-rose-800/60',
  blue: 'bg-sky-950 text-sky-300 border-sky-800/60',
  violet: 'bg-purple-950 text-purple-300 border-purple-800/60',
  gray: 'bg-slate-800 text-slate-300 border-slate-700/60',
};

export function Badge({
  tone = 'gray',
  variant,
  className,
  children,
}: {
  tone?: BadgeTone;
  variant?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border", STYLES[tone], className)}>
      {children}
    </span>
  );
}
