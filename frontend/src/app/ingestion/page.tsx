"use client";
import React, { useState } from "react";
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
  Button,
} from "@/components/ui";
import { Database, Play, CheckCircle2, RefreshCw } from "lucide-react";
import { getIngestionStatus, getFlaggedRecords } from "@/lib/api/ingestion";
import { useFetch } from "@/hooks/useFetch";
import { LoadState } from "@/components/ui/LoadState";
import { FlaggedRecord } from "@/types/ingestion";

export default function IngestionPage() {
  const streams = useFetch(getIngestionStatus);
  const request = useFetch(getFlaggedRecords);
  const records = request.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F1"
        title="Streaming Ingestion & Schema Gate"
        description="High-throughput Kafka stream consumers, real-time schema validation, and early duplicate rejection."
        actions={
          <Button
            onClick={() => {
              void streams.refetch();
              void request.refetch();
            }}
          >
            Refresh
          </Button>
        }
      />
      <LoadState
        {...streams}
        resource="Stream status"
        empty={streams.data?.length === 0}
      />

      {/* Stream Topics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {(streams.data ?? []).map((st) => (
          <Card key={st.topic}>
            <CardContent className="p-4 space-y-2">
              <div className="flex justify-between items-start">
                <span className="font-mono text-xs font-semibold text-slate-200">
                  {st.topic}
                </span>
                <Badge tone={st.status === "active" ? "green" : "amber"}>
                  {st.status}
                </Badge>
              </div>
              <div className="flex justify-between text-xs text-slate-400 pt-2">
                <span>Ingest Rate:</span>
                <span className="font-mono text-slate-200">{st.rate}</span>
              </div>
              <div className="flex justify-between text-xs text-slate-400">
                <span>Consumer Lag:</span>
                <span className="font-mono text-slate-200">{st.lag} msgs</span>
              </div>
              <div className="flex justify-between text-xs text-slate-400">
                <span>Validation Errors:</span>
                <span className="font-mono text-rose-300">{st.errorCount}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Flagged Records Table */}
      <Card>
        <CardHeader
          title="Flagged Records & Ingestion Autopsy"
          subtitle="Records failing range validation, schema conformance, or duplicate bounds"
        />
        <CardContent className="p-0">
          <LoadState
            {...request}
            resource="Flagged records"
            empty={request.data?.length === 0}
          />
          {!!records.length && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Record ID</TableHead>
                  <TableHead>Source Adapter</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reason Column</TableHead>
                  <TableHead>Timestamp</TableHead>
                </TableRow>
              </TableHeader>
              <tbody>
                {records.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-sky-400 font-semibold">
                      {r.id}
                    </TableCell>
                    <TableCell>{r.source}</TableCell>
                    <TableCell>
                      <Badge
                        tone={
                          r.status === "Valid"
                            ? "green"
                            : r.status === "Invalid"
                              ? "red"
                              : "amber"
                        }
                      >
                        {r.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-300">{r.reason}</TableCell>
                    <TableCell className="font-mono text-slate-400">
                      {r.time}
                    </TableCell>
                  </TableRow>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
