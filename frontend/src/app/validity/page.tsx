'use client';
import React, { useState } from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Table, TableHeader, TableRow, TableHead, TableCell, Button } from '@/components/ui';
import { ValidityBadge } from '@/components/validity/ValidityBadge';
import { RefreshCw } from 'lucide-react';
import { MOCK_DECISIONS } from '@/lib/fixtures';
import { reverifyDecision } from '@/lib/api/validity';

export default function ValidityListPage() {
  const [decisions, setDecisions] = useState(MOCK_DECISIONS);
  const [reverifying, setReverifying] = useState(false);

  const handleReverifyAll = async () => {
    setReverifying(true);
    await new Promise(r => setTimeout(r, 600));
    setDecisions(decisions.map(d => ({
      ...d,
      status: d.id === 'DEC-802' ? 'verified' : d.status
    })));
    setReverifying(false);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F3 · USP 2"
        title="Decision Validity Tracking"
        description="Deterministic dependency tracking. Outputs automatically flag as stale or invalidated when input assumptions change."
        actions={
          <Button size="sm" variant="primary" loading={reverifying} onClick={handleReverifyAll}>
            <RefreshCw size={14} className="mr-1.5" /> Re-Verify Affected Results
          </Button>
        }
      />

      <Card>
        <CardHeader title="Tracked Decisions & Validity Status" subtitle="Governed operational decisions requiring continuous validation" />
        <CardContent className="p-0">
          <Table>
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
                  <TableCell className="font-mono text-sky-400 font-semibold">{dec.id}</TableCell>
                  <TableCell>{dec.type}</TableCell>
                  <TableCell className="font-mono">v{dec.version}</TableCell>
                  <TableCell>
                    <ValidityBadge status={dec.status} />
                  </TableCell>
                  <TableCell className="font-mono text-slate-400">{dec.createdAt}</TableCell>
                  <TableCell>
                    <Link href={`/validity/${dec.id}`}>
                      <Button variant="outline" size="sm">Inspect Detail →</Button>
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
