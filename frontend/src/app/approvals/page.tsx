"use client";
import { useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout";
import { Button, Card, CardHeader, CardContent } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { ApprovalPanel } from "@/components/approvals/ApprovalPanel";
import { VerificationBadge } from "@/components/validity/VerificationBadge";
import { ScheduleGantt } from "@/components/charts";
import { useFetch } from "@/hooks/useFetch";
import { useApproval } from "@/hooks/useApproval";
import { getApprovals, type ApprovalItem } from "@/lib/api/approvals";
import { getSchedule } from "@/lib/api/planning";
import { checkVerification } from "@/lib/api/verification";
export default function ApprovalsPage() {
  const request = useFetch(getApprovals);
  const [active, setActive] = useState<ApprovalItem | null>(null);
  const pending =
    request.data?.filter((item) => item.status === "pending") ?? [];
  return (
    <div className="space-y-6">
      <PageHeader
        title="Approval queue"
        description="Review evidence and verification before approving a result. Rationale is required for every decision."
      />
      <LoadState
        {...request}
        resource="Approval queue"
        empty={!!request.data && !pending.length}
      />
      {active && (
        <Review
          key={active.id}
          item={active}
          done={() => {
            setActive(null);
            void request.refetch();
          }}
        />
      )}
      {request.data && pending.length > 0 && (
        <>
          <Card>
            <CardHeader title="Results awaiting review" />
            <CardContent>
              <ul className="space-y-4">
                {pending.map((item) => (
                  <li
                    key={item.id}
                    className="flex flex-wrap gap-4 items-center border-b border-slate-800 pb-4"
                  >
                    <div className="flex-1">
                      <p>
                        {item.targetId} &middot; {item.type}
                      </p>
                      <p className="text-sm text-slate-400">{item.summary}</p>
                      <p className="text-xs text-slate-400">
                        {item.submittedBy} &middot; {item.submittedAt}
                      </p>
                    </div>
                    <VerificationBadge status={item.verification} />
                    <Button onClick={() => setActive(item)}>Review</Button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
function Review({ item, done }: { item: ApprovalItem; done: () => void }) {
  const approval = useApproval();
  const verification = useFetch(
    () =>
      checkVerification({
        target_type: item.targetId.startsWith("SCH") ? "schedule" : "decision",
        target_id: item.targetId,
      }),
    [item.id],
  );
  const schedule = useFetch(
    () =>
      item.targetId.startsWith("SCH")
        ? getSchedule(item.targetId)
        : Promise.resolve(null),
    [item.id],
  );
  const result = verification.data;
  return (
    <div className="space-y-4 border border-slate-700 p-4 rounded">
      <Button variant="ghost" disabled={approval.submitting} onClick={done}>
        Close review
      </Button>
      <Card>
        <CardHeader title="Schedule, evidence & verifier output" />
        <CardContent>
          <LoadState {...schedule} resource="Schedule details" />
          <LoadState {...verification} resource="Verifier results" />
          {schedule.data && (
            <ScheduleGantt
              assignments={schedule.data.assignments}
              horizon={Math.max(
                1,
                ...schedule.data.assignments.map((a) => a.end),
              )}
            />
          )}
          {result && (
            <div className="space-y-3">
              <p>
                Verifier outcome: <VerificationBadge status={result.outcome} />
              </p>
              <h3>Uncertainty flags</h3>
              <ul>
                {result.uncertainty_flags.map((flag) => (
                  <li key={flag}>{flag}</li>
                ))}
              </ul>
              {!result.uncertainty_flags.length && (
                <p className="text-sm text-slate-400">
                  No uncertainty flags reported.
                </p>
              )}
              <h3>Violations & evidence</h3>
              {result.violations.map((violation, i) => (
                <div key={i}>
                  <p>
                    {violation.rule}: {violation.message}
                  </p>
                  {violation.refs.map((ref) => (
                    <Link
                      key={ref}
                      className="text-sky-300 mr-3"
                      href={`/evidence/${encodeURIComponent(ref)}`}
                    >
                      {ref}
                    </Link>
                  ))}
                </div>
              ))}
              {!result.violations.length && (
                <p className="text-sm text-slate-400">
                  No violations reported.
                </p>
              )}
            </div>
          )}
          <Link
            href={`/audit?entity=${encodeURIComponent(item.targetId)}`}
            className="text-sky-300"
          >
            Related evidence and audit history
          </Link>
        </CardContent>
      </Card>
      <ApprovalPanel
        targetId={item.targetId}
        title={item.summary}
        verification={
          verification.error || verification.loading
            ? "uncertain"
            : (result?.outcome ?? "uncertain")
        }
        loading={approval.submitting}
        onApprove={async (reviewer, rationale) => {
          const ok = await approval.approve(
            item.id,
            reviewer,
            rationale,
            result?.outcome ?? "uncertain",
          );
          if (ok) done();
          return ok;
        }}
        onReject={async (reviewer, rationale) => {
          const ok = await approval.reject(item.id, reviewer, rationale);
          if (ok) done();
          return ok;
        }}
      />
      {approval.error && (
        <LoadState
          loading={false}
          error={approval.error}
          resource="Review submission"
          action
        />
      )}
      {approval.feedback && <p role="status">{approval.feedback}</p>}
    </div>
  );
}
