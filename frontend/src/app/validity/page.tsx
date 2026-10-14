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
  Button,
} from "@/components/ui";
import { ValidityBadge } from "@/components/validity/ValidityBadge";
import { RefreshCw } from "lucide-react";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";
import { getDecisions, reverifyDecision } from "@/lib/api/validity";

export default function ValidityListPage() {
  const request = useFetch(getDecisions);
  const decisions = request.data ?? [];
  const [reverifying, setReverifying] = useState(false);
  const [error, setError] = useState<Error | string | null>(null);
  const handleReverifyAll = async () => {
    setReverifying(true);
    setError(null);
    try {
      await Promise.all(
        decisions
          .filter((d) => d.status !== "verified")
          .map((d) => reverifyDecision(d.id)),
      );
      await request.refetch();
    } catch (err) {
      setError(err instanceof Error ? err : "Re-verification failed");
    } finally {
      setReverifying(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F3 · USP 2"
        title="Decision Validity Tracking"
        description="Deterministic dependency tracking. Outputs automatically flag as stale or invalidated when input assumptions change."
        actions={
          <Button
            size="sm"
            variant="primary"
            loading={reverifying}
            onClick={handleReverifyAll}
          >
            <RefreshCw size={14} className="mr-1.5" /> Re-Verify Affected
            Results
          </Button>
        }
      />

      <LoadState
        {...request}
        error={error ?? request.error}
        empty={decisions.length === 0}
      />
      {request.data && decisions.length > 0 && (
        <>
          <Card>
            <CardHeader
              title="Tracked Decisions & Validity Status"
              subtitle="Governed operational decisions requiring continuous validation"
            />
            <CardContent className="p-0">
              <Table className="validity-table">
                <colgroup>
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "21%" }} />
                  <col style={{ width: "11%" }} />
                  <col style={{ width: "15%" }} />
                  <col style={{ width: "24%" }} />
                  <col style={{ width: "15%" }} />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead>Decision ID</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created At</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <tbody>
                  {decisions.map((dec) => (
                    <TableRow key={dec.id}>
                      <TableCell className="font-mono text-sky-400 font-semibold">
                        {dec.id}
                      </TableCell>
                      <TableCell>{dec.type}</TableCell>
                      <TableCell className="font-mono">
                        v{dec.version}
                      </TableCell>
                      <TableCell>
                        <ValidityBadge status={dec.status} />
                      </TableCell>
                      <TableCell className="font-mono text-slate-400">
                        {dec.createdAt}
                      </TableCell>
                      <TableCell>
                        <Link href={`/validity/${dec.id}`}>
                          <span className="inline-flex items-center rounded border border-slate-700 px-3 py-2 text-xs text-sky-300 hover:bg-slate-800">
                            Inspect Detail →
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
