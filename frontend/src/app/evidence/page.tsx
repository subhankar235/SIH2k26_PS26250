"use client";
import React, { useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout";
import {
  Card,
  CardHeader,
  CardContent,
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableCell,
  Badge,
} from "@/components/ui";
import { getIssues } from "@/lib/api/evidence";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";

export default function EvidencePage() {
  const request = useFetch(getIssues);
  const issues = request.data ?? [];
  const [filterClass, setFilterClass] = useState<string>("all");

  const filtered =
    filterClass === "all"
      ? issues
      : issues.filter((i) => i.issueClass === filterClass);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F2 · USP 1"
        title="Evidence Intelligence & Contradiction Autopsy"
        description="Explicit provenance tracking and contradiction management. Competing claims are compared transparently without silent resolution."
      />

      {/* Filters Toolbar */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-900/60 border border-slate-800 p-3 rounded">
        <span className="text-xs text-slate-400 font-medium">
          Filter by Issue Class:
        </span>
        {(["all", "conflict", "stale", "missing", "duplicate"] as const).map(
          (cls) => (
            <button
              key={cls}
              aria-pressed={filterClass === cls}
              onClick={() => setFilterClass(cls)}
              className={`px-2.5 py-1 rounded text-xs uppercase font-mono transition-colors ${
                filterClass === cls
                  ? "bg-sky-600 text-white font-semibold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {cls}
            </button>
          ),
        )}
      </div>

      <LoadState {...request} />
      {request.data && (
        <>
          <Card>
            <CardHeader
              title="Open Evidence Issues"
              subtitle="Click any record to inspect the complete Contradiction Autopsy"
            />
            <CardContent className="p-0">
              <Table className="evidence-table">
                <colgroup>
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "12%" }} />
                  <col style={{ width: "23%" }} />
                  <col style={{ width: "20%" }} />
                  <col style={{ width: "15%" }} />
                  <col style={{ width: "16%" }} />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead>Issue ID</TableHead>
                    <TableHead>Class</TableHead>
                    <TableHead>Affected Resource</TableHead>
                    <TableHead>Source Lineage</TableHead>
                    <TableHead>Detected At</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <tbody>
                  {filtered.length === 0 && (
                    <TableRow>
                      <td colSpan={6} className="evidence-empty">
                        <p role="status">No results</p>
                        <p>No evidence issues match this filter.</p>
                      </td>
                    </TableRow>
                  )}
                  {filtered.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-sky-400 font-semibold">
                        {item.id}
                      </TableCell>
                      <TableCell>
                        <Badge
                          tone={
                            item.issueClass === "conflict"
                              ? "red"
                              : item.issueClass === "stale"
                                ? "amber"
                                : "blue"
                          }
                        >
                          {item.issueClass}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-slate-200">
                        {item.affectedResource}
                      </TableCell>
                      <TableCell className="text-slate-400">
                        {item.sourceId}
                      </TableCell>
                      <TableCell className="font-mono text-slate-400">
                        {item.detectedAt}
                      </TableCell>
                      <TableCell>
                        <Link href={`/evidence/${item.id}`}>
                          <span className="inline-flex items-center rounded border border-slate-700 px-3 py-2 text-xs text-sky-300 hover:bg-slate-800">
                            Inspect Autopsy →
                          </span>
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
