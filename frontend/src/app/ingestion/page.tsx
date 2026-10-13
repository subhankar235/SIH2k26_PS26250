'use client';
import React, { useState } from 'react';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Table, TableHeader, TableRow, TableHead, TableCell, Badge, Button } from '@/components/ui';
import { Database, Play, CheckCircle2, RefreshCw } from 'lucide-react';
import { MOCK_STREAMS, MOCK_RECORDS } from '@/lib/fixtures';
import { FlaggedRecord } from '@/types/ingestion';

export default function IngestionPage() {
  const [records, setRecords] = useState<FlaggedRecord[]>(MOCK_RECORDS);
  const [replaying, setReplaying] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const handleReplay = () => {
    setReplaying(true);
    setTimeout(() => {
      const newRec: FlaggedRecord = {
        id: `REC-${1052 + records.length}`,
        source: 'Resource registry',
        time: new Date().toLocaleTimeString(),
        status: 'Valid',
        version: 1,
        duplicate: false,
        reason: 'Replayed synthetic event verified against schema v1',
      };
      setRecords([newRec, ...records]);
      setReplaying(false);
      setNotification(`Event ${newRec.id} appended to stream and schema validated.`);
      setTimeout(() => setNotification(null), 4000);
    }, 600);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F1"
        title="Streaming Ingestion & Schema Gate"
        description="High-throughput Kafka stream consumers, real-time schema validation, and early duplicate rejection."
        actions={
          <Button size="sm" variant="primary" loading={replaying} onClick={handleReplay}>
            <Play size={14} className="mr-1.5" /> Replay Event
          </Button>
        }
      />

      {notification && (
        <div className="p-3 bg-emerald-950/40 border border-emerald-800/80 rounded text-xs text-emerald-300 flex items-center gap-2">
          <CheckCircle2 size={16} className="text-emerald-400" />
          <span>{notification}</span>
        </div>
      )}

      {/* Stream Topics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {MOCK_STREAMS.map((st) => (
          <Card key={st.topic}>
            <CardContent className="p-4 space-y-2">
              <div className="flex justify-between items-start">
                <span className="font-mono text-xs font-semibold text-slate-200">{st.topic}</span>
                <Badge tone={st.status === 'active' ? 'green' : 'amber'}>{st.status}</Badge>
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
                  <TableCell className="font-mono text-sky-400 font-semibold">{r.id}</TableCell>
                  <TableCell>{r.source}</TableCell>
                  <TableCell>
                    <Badge tone={r.status === 'Valid' ? 'green' : r.status === 'Invalid' ? 'red' : 'amber'}>
                      {r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-slate-300">{r.reason}</TableCell>
                  <TableCell className="font-mono text-slate-400">{r.time}</TableCell>
                </TableRow>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
