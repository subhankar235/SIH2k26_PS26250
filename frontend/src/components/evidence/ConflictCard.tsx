import React from 'react';
import { Card, CardHeader, CardContent, Badge } from '@/components/ui';
import { Claim } from '@/types/evidence';

export function ConflictCard({ claims }: { claims: Claim[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {claims.map((claim, index) => (
        <Card key={claim.id} className="border-amber-900/40 bg-amber-950/10">
          <CardHeader
            title={`Claim ${String.fromCharCode(65 + index)}: ${claim.attribute}`}
            subtitle={`Source: ${claim.sourceId}`}
            action={<Badge tone="amber">Competing</Badge>}
          />
          <CardContent>
            <div className="text-xl font-bold font-mono text-slate-100">{claim.value}</div>
            <p className="text-xs text-slate-400 mt-2">Recorded at: {claim.observedAt}</p>
            {claim.supersededBy && (
              <p className="text-xs text-rose-400 mt-1">Superseded by {claim.supersededBy}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
