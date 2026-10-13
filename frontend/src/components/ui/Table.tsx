import React from 'react';
import { cn } from '@/lib/utils';

export function Table({ className, children }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-left text-sm text-slate-300", className)}>
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ children }: { children: React.ReactNode }) {
  return <thead className="bg-slate-950/60 border-b border-slate-800 text-xs uppercase text-slate-400">{children}</thead>;
}

export function TableRow({ className, children, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors", className)} {...props}>{children}</tr>;
}

export function TableHead({ className, children }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("px-4 py-3 font-medium", className)}>{children}</th>;
}

export function TableCell({ className, children }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3 align-middle", className)}>{children}</td>;
}
