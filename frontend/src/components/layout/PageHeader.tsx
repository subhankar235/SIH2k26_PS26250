import React from "react";

export interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800/80">
      <div className="min-w-0 break-words">
        {eyebrow && (
          <span className="text-[11px] uppercase tracking-wider font-semibold text-sky-400">
            {eyebrow}
          </span>
        )}
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">
          {title}
        </h1>
        {description && (
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2.5">{actions}</div>
      )}
    </div>
  );
}
