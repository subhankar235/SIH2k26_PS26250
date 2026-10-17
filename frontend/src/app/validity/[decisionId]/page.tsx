"use client";
import { use, useState } from "react";
import { PageHeader } from "@/components/layout";
import { Card, CardHeader, CardContent, Button } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { ValidityBadge, DependencyGraphView } from "@/components/validity";
import { useFetch } from "@/hooks/useFetch";
import { getDecision, reverifyDecision } from "@/lib/api/validity";
import { getAuditEntries } from "@/lib/api/audit";
export default function ValidityDetailPage({
  params,
}: {
  params: Promise<{ decisionId: string }>;
}) {
  const { decisionId } = use(params);
  const request = useFetch(() => getDecision(decisionId), [decisionId]);
  const history = useFetch(getAuditEntries, [decisionId]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | string | null>(null);
  async function reverify() {
    setBusy(true);
    setError(null);
    try {
      await reverifyDecision(decisionId);
      await Promise.all([request.refetch(), history.refetch()]);
    } catch (err) {
      setError(err instanceof Error ? err : "Re-verification failed");
    } finally {
      setBusy(false);
    }
  }
  const decision = request.data;
  const changes =
    history.data?.filter((e) => e.entity.includes(decisionId)) ?? [];
  return (
    <div className="space-y-6">
      <PageHeader
        title={`Decision: ${decisionId}`}
        description="Assumptions, versioned dependencies, and recorded status changes."
        actions={
          <Button loading={busy} disabled={!decision} onClick={reverify}>
            Re-verify
          </Button>
        }
      />
      <LoadState
        {...request}
        resource="Decision details"
        error={error ?? request.error}
      />
      {decision && (
        <>
          <Card>
            <CardHeader
              title={decision.type}
              action={<ValidityBadge status={decision.status} />}
            />
            <CardContent>
              <p>
                Version {decision.version} &middot; {decision.createdAt}
              </p>
              <h2 className="mt-4 font-semibold">Assumptions</h2>
              <ul>
                {decision.assumptions.map((a) => (
                  <li key={a.id} className="py-2">
                    {a.id}: {a.description}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <DependencyGraphView decision={decision} />
        </>
      )}
      <Card>
        <CardHeader title="Status-change history" />
        <CardContent>
          <LoadState
            {...history}
            resource="Status-change history"
            empty={!changes.length}
          />
          <ul>
            {changes.map((entry) => (
              <li key={entry.id} className="py-2 text-sm">
                {entry.timestamp} &middot; {entry.action} ({entry.actor})
                {entry.details && <p>{entry.details}</p>}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
