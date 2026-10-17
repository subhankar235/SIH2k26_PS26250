"use client";
import React, { use } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout";
import { Card, CardHeader, CardContent, Button, Badge } from "@/components/ui";
import {
  ConflictCard,
  ProvenanceTimeline,
  EvidenceGraph,
} from "@/components/evidence";
import { ArrowLeft, Clock3 } from "lucide-react";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";
import { getAutopsy } from "@/lib/api/evidence";

export default function EvidenceAutopsyPage({
  params,
}: {
  params: Promise<{ recordId: string }>;
}) {
  const { recordId } = use(params);
  const {
    data: autopsy,
    loading,
    error,
    refetch,
  } = useFetch(() => getAutopsy(recordId), [recordId]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xs">
        <Link
          href="/evidence"
          className="text-slate-400 hover:text-slate-200 flex items-center gap-1"
        >
          <ArrowLeft size={14} /> Back to Evidence List
        </Link>
      </div>

      <PageHeader
        eyebrow="EVIDENCE AUTOPSY"
        title={`Contradiction Autopsy: ${recordId}`}
        description="Comprehensive forensic view of contradictory claims, source lineage, uncertainty estimates, and missing information."
        actions={
          <Link href={`/audit?entity=${encodeURIComponent(recordId)}`}>
            <span className="inline-flex items-center rounded border border-slate-700 px-3 py-2 text-xs text-sky-300 hover:bg-slate-800">
              <Clock3 size={14} className="mr-1.5" /> View Audit Trail
            </span>
          </Link>
        }
      />

      {error ? (
        <LoadState loading={false} error={error} refetch={refetch} />
      ) : loading || !autopsy ? (
        <Card>
          <CardContent className="p-8 text-center text-slate-400">
            Loading autopsy forensic data...
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Side by side conflicting claims */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-200">
              Competing Claims (Unresolved Disagreement)
            </h3>
            <ConflictCard claims={autopsy.claims} />
          </div>

          {/* Evidence Graph & Provenance Timeline */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader title="Source evidence" />
              <CardContent>
                <ul>
                  {autopsy.claims.map((claim) => (
                    <li key={claim.id} className="text-sm py-2">
                      {claim.sourceId} &middot; {claim.id} &middot; {recordId}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader
                title="Provenance Timeline"
                subtitle="Transformation and arrival history"
              />
              <CardContent>
                <ProvenanceTimeline steps={autopsy.provenance} />
              </CardContent>
            </Card>
          </div>

          {/* Missing info & Uncertainty */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader
                title="Missing Information"
                subtitle="Reconciliation evidence required for resolution"
              />
              <CardContent>
                <ul className="list-disc list-inside space-y-1.5 text-xs text-slate-300">
                  {autopsy.missingInformation.map((info, idx) => (
                    <li key={idx}>{info}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader
                title="Quantified Uncertainty"
                subtitle="Probabilistic error and noise bounds"
              />
              <CardContent className="space-y-3">
                {autopsy.uncertainty.map((u, i) => (
                  <div
                    key={i}
                    className="flex justify-between items-center text-xs"
                  >
                    <span className="text-slate-400">{u.label}</span>
                    <Badge tone="amber">{(u.value * 100).toFixed(1)}%</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
