'use client';
import React, { useState } from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Table, TableHeader, TableRow, TableHead, TableCell, Badge, Button } from '@/components/ui';
import { MOCK_ISSUES } from '@/lib/fixtures';
import { IssueClass } from '@/types/evidence';

export default function EvidencePage() {
  const [filterClass, setFilterClass] = useState<string>('all');

  const filtered = filterClass === 'all'
    ? MOCK_ISSUES
    : MOCK_ISSUES.filter(i => i.issueClass === filterClass);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F2 · USP 1"
        title="Evidence Intelligence & Contradiction Autopsy"
        description="Explicit provenance tracking and contradiction management. Competing claims are compared transparently without silent resolution."
      />

      {/* Filters Toolbar */}
      <div className="flex items-center gap-3 bg-slate-900/60 border border-slate-800 p-3 rounded">
        <span className="text-xs text-slate-400 font-medium">Filter by Issue Class:</span>
        {(['all', 'conflict', 'stale', 'missing', 'duplicate'] as const).map(cls => (
          <button
            key={cls}
            onClick={() => setFilterClass(cls)}
            className={`px-2.5 py-1 rounded text-xs uppercase font-mono transition-colors ${
              filterClass === cls
                ? 'bg-sky-600 text-white font-semibold'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {cls}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader title="Open Evidence Issues" subtitle="Click any record to inspect the complete Contradiction Autopsy" />
        <CardContent className="p-0">
          <Table>
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
              {filtered.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono text-sky-400 font-semibold">{item.id}</TableCell>
                  <TableCell>
                    <Badge tone={item.issueClass === 'conflict' ? 'red' : item.issueClass === 'stale' ? 'amber' : 'blue'}>
                      {item.issueClass}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-slate-200">{item.affectedResource}</TableCell>
                  <TableCell className="text-slate-400">{item.sourceId}</TableCell>
                  <TableCell className="font-mono text-slate-400">{item.detectedAt}</TableCell>
                  <TableCell>
                    <Link href={`/evidence/${item.id}`}>
                      <Button variant="outline" size="sm">Inspect Autopsy →</Button>
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
