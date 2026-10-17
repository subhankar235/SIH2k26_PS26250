"use client";
import React, { useState, useEffect } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardHeader, CardContent, Spinner, Badge } from "@/components/ui";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";
import { getAuditEntries } from "@/lib/api/audit";
import { AuditEntry } from "@/types/audit";
import { ShieldCheck, Search, Filter, Lock } from "lucide-react";

export default function AuditPage() {
  const request = useFetch(getAuditEntries);
  const entries = request.data ?? [];
  const loading = request.loading;
  const [query, setQuery] = useState("");
  const [actorFilter, setActorFilter] = useState("all");

  useEffect(() => {
    setQuery(new URLSearchParams(window.location.search).get("entity") ?? "");
  }, []);
  const [actionFilter, setActionFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("");

  const filtered = entries.filter((e) => {
    const matchesQuery =
      e.id.toLowerCase().includes(query.toLowerCase()) ||
      e.entity.toLowerCase().includes(query.toLowerCase()) ||
      e.action.toLowerCase().includes(query.toLowerCase()) ||
      e.actor.toLowerCase().includes(query.toLowerCase());

    const matchesActor =
      actorFilter === "all" ||
      (actorFilter === "system" &&
        (e.actor.includes("Engine") || e.actor.includes("Service"))) ||
      (actorFilter === "human" &&
        !e.actor.includes("Engine") &&
        !e.actor.includes("Service"));

    return (
      matchesQuery &&
      matchesActor &&
      (actionFilter === "all" || e.action === actionFilter) &&
      (!dateFilter || e.timestamp.startsWith(dateFilter))
    );
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Immutable Audit Trail (F9)"
        description="Read-only event history across actors, decisions, and policies"
        actions={
          <Badge
            variant="outline"
            className="border-emerald-800 text-emerald-300"
          >
            <Lock size={12} className="mr-1 inline" /> Read-Only • Tamper-Proof
          </Badge>
        }
      />

      <LoadState {...request} empty={!loading && !filtered.length} />
      {/* Search & Filter */}
      <Card className="border-slate-800 bg-slate-900/40">
        <CardContent className="pt-4">
          <div className="flex flex-col md:flex-row gap-3">
            <div className="flex-1 relative">
              <Search
                size={14}
                className="absolute left-3 top-2.5 text-slate-500"
              />
              <input
                aria-label="Search audit records"
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search audit logs by ID, entity, action, or actor..."
                className="w-full bg-slate-950 border border-slate-700 rounded pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div className="w-48">
              <select
                aria-label="Actor filter"
                value={actorFilter}
                onChange={(e) => setActorFilter(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              >
                <option value="all">All Actors</option>
                <option value="system">System / Automated Engines</option>
                <option value="human">Human Operators</option>
              </select>
            </div>
            <label className="text-xs">
              Action
              <select
                className="block bg-slate-950 p-2"
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
              >
                <option value="all">All actions</option>
                {Array.from(new Set(entries.map((e) => e.action))).map(
                  (action) => (
                    <option key={action}>{action}</option>
                  ),
                )}
              </select>
            </label>
            <label className="text-xs">
              Date
              <input
                type="date"
                className="block bg-slate-950 p-2"
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
              />
            </label>
          </div>
        </CardContent>
      </Card>

      {request.data && filtered.length > 0 && (
        <>
          {/* Read-Only Table */}
          <Card className="border-slate-800">
            <CardHeader
              title="Audit Log Records"
              subtitle="Strict Rule: Edit and delete operations are strictly prohibited on this ledger"
            />
            <CardContent>
              {loading ? (
                <div className="py-12 flex justify-center">
                  <Spinner />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 uppercase font-semibold">
                      <tr>
                        <th className="px-4 py-2.5">Log ID</th>
                        <th className="px-4 py-2.5">Entity</th>
                        <th className="px-4 py-2.5">Action Executed</th>
                        <th className="px-4 py-2.5">Actor</th>
                        <th className="px-4 py-2.5">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {filtered.map((e) => (
                        <tr key={e.id} className="hover:bg-slate-800/30">
                          <td className="px-4 py-3 font-semibold text-sky-400">
                            {e.id}
                          </td>
                          <td className="px-4 py-3 font-sans text-slate-200">
                            {e.entity}
                          </td>
                          <td className="px-4 py-3 font-sans text-slate-300">
                            {e.action}
                          </td>
                          <td className="px-4 py-3 font-sans">
                            <span
                              className={
                                e.actor.includes("Engine") ||
                                e.actor.includes("Service")
                                  ? "text-indigo-400"
                                  : "text-emerald-400"
                              }
                            >
                              {e.actor}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-400">
                            {e.timestamp}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
