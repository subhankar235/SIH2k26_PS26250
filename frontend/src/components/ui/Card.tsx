import React from 'react';
import { cn } from '@/lib/utils';

export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("bg-slate-900 border border-slate-800 rounded-lg shadow-md overflow-hidden", className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ className, title, subtitle, action, children }: { className?: string; title?: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className={cn("p-4 border-b border-slate-800/80 flex items-start justify-between gap-4", className)}>
      <div>
        {title && <h3 className="font-semibold text-slate-100 text-base">{title}</h3>}
        {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        {children}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

export function CardContent({ className, children }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)}>{children}</div>;
}

export function CardFooter({ className, children }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-3 bg-slate-950/40 border-t border-slate-800/60 text-xs text-slate-400", className)}>{children}</div>;
}
