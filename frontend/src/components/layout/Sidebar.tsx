'use client';
import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Wind,
  LayoutDashboard,
  Database,
  Network,
  ShieldCheck,
  ChartNoAxesCombined,
  SlidersHorizontal,
  GitBranch,
  Box,
  Activity,
  ClipboardCheck,
  Clock3,
  ChartColumn,
  ChevronDown,
  Menu,
  X
} from 'lucide-react';
import { NAVIGATION_ITEMS, APP_NAME, APP_SUBTITLE } from '@/lib/constants';

const ICONS: Record<string, React.ElementType> = {
  LayoutDashboard,
  Database,
  Network,
  ShieldCheck,
  ChartNoAxesCombined,
  SlidersHorizontal,
  GitBranch,
  Box,
  Activity,
  ClipboardCheck,
  Clock3,
  ChartColumn,
};

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Mobile Toggle Button */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="lg:hidden fixed top-3 left-4 z-50 p-2 bg-slate-900 border border-slate-800 rounded text-slate-300 hover:text-white"
        aria-label="Toggle navigation"
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Backdrop */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
        />
      )}

      {/* Sidebar Shell */}
      <aside
        className={`fixed top-0 left-0 bottom-0 z-40 w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col transition-transform duration-200 lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <Link href="/" onClick={() => setMobileOpen(false)} className="flex items-center gap-2.5">
            <div className="p-2 bg-sky-500/10 border border-sky-500/30 rounded text-sky-400">
              <Wind size={22} />
            </div>
            <div>
              <div className="font-bold tracking-wider text-slate-100 text-sm">{APP_NAME}</div>
              <div className="text-[10px] tracking-widest text-slate-400">{APP_SUBTITLE}</div>
            </div>
          </Link>
        </div>

        {/* Workspace Selector */}
        <div className="px-4 py-3 border-b border-slate-800/60 bg-slate-900/40 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded bg-sky-600/30 text-sky-300 font-semibold flex items-center justify-center text-[10px]">S</span>
            <div>
              <p className="font-medium text-slate-200">Synthetic workspace</p>
              <p className="text-[10px] text-slate-500">Defense & Operations</p>
            </div>
          </div>
          <ChevronDown size={14} className="text-slate-500" />
        </div>

        {/* Navigation list */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6" aria-label="Main navigation">
          {NAVIGATION_ITEMS.map((group) => (
            <div key={group.group}>
              <div className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                {group.group}
              </div>
              <ul className="space-y-0.5">
                {group.items.map((rawItem) => {
                  const item = rawItem as { href: string; label: string; icon: string; count?: number; badge?: string };
                  const Icon = ICONS[item.icon] || LayoutDashboard;
                  const isActive = pathname === item.href;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={() => setMobileOpen(false)}
                        className={`flex items-center justify-between px-2.5 py-1.5 rounded text-xs transition-colors ${
                          isActive
                            ? 'bg-sky-500/15 text-sky-300 font-medium border border-sky-500/30'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon size={16} className={isActive ? 'text-sky-400' : 'text-slate-500'} />
                          <span>{item.label}</span>
                        </div>
                        {Boolean(item.count) && (
                          <span className="px-1.5 py-0.2 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded text-[10px]">
                            {item.count}
                          </span>
                        )}
                        {Boolean(item.badge) && (
                          <span className="px-1.5 py-0.2 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded text-[10px]">
                            {item.badge}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* User profile footer */}
        <div className="p-3 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-semibold text-slate-300">
              KD
            </div>
            <div className="text-left text-xs">
              <p className="font-medium text-slate-300 leading-tight">Kathakali Das</p>
              <p className="text-[10px] text-slate-500">Lead Analyst · Online</p>
            </div>
          </div>
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
        </div>
      </aside>
    </>
  );
}
