'use client';
import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Search, Radio, Shield, Bell } from 'lucide-react';
import { NAVIGATION_ITEMS } from '@/lib/constants';

export function Navbar() {
  const pathname = usePathname();
  const [search, setSearch] = useState('');

  // Find active label
  let currentLabel = 'Overview';
  for (const group of NAVIGATION_ITEMS) {
    for (const it of group.items) {
      if (it.href === pathname) currentLabel = it.label;
    }
  }

  const allItems = NAVIGATION_ITEMS.flatMap(g => g.items);
  const searchResults = search.trim()
    ? allItems.filter(i => i.label.toLowerCase().includes(search.toLowerCase()))
    : [];

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/90 backdrop-blur sticky top-0 z-30 px-4 lg:px-6 flex items-center justify-between">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs pl-8 lg:pl-0">
        <span className="text-slate-500">Platform</span>
        <span className="text-slate-600">/</span>
        <span className="font-semibold text-slate-200">{currentLabel}</span>
      </div>

      {/* Middle Search */}
      <div className="relative max-w-xs w-full hidden sm:block">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search decisions, evidence, routes..."
            className="w-full bg-slate-900 border border-slate-800 rounded pl-8 pr-3 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
        </div>
        {searchResults.length > 0 && (
          <div className="absolute top-9 left-0 right-0 bg-slate-900 border border-slate-800 rounded shadow-xl p-1 z-50">
            {searchResults.map(res => (
              <Link
                key={res.href}
                href={res.href}
                onClick={() => setSearch('')}
                className="block px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 rounded"
              >
                {res.label}
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-[11px] px-2.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 font-mono">
          <Radio size={12} className="animate-pulse text-emerald-400" />
          LIVE SYNTHETIC FEED
        </div>
        <Link href="/approvals" className="p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-900 relative">
          <Bell size={16} />
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-amber-400" />
        </Link>
        <div className="text-xs text-slate-400 hidden md:block">
          Cluster: <span className="font-mono text-slate-200">AIR-IN-01</span>
        </div>
      </div>
    </header>
  );
}
