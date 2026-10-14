"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CloudOff, RefreshCw, ArrowUpRight, Info } from "lucide-react";
import { failureDetails, type RequestFailure } from "@/lib/request-failure";
const views: Record<string, string> = {
  ingestion: "Ingestion activity",
  evidence: "Evidence records",
  validity: "Decision validity",
  forecasts: "Forecasts",
  planning: "Schedule planning",
  "stress-lab": "Stress experiments",
  explanations: "Agent explanations",
  approvals: "Approval queue",
  audit: "Audit history",
  benchmarks: "Benchmark results",
};
export function ErrorState({
  title,
  message,
  onRetry,
  resource,
  hasData = false,
  action = false,
}: {
  title?: string;
  message: RequestFailure;
  onRetry?: () => void | Promise<void>;
  resource?: string;
  hasData?: boolean;
  action?: boolean;
}) {
  const pathname = usePathname();
  const area = resource ?? views[pathname.split("/")[1]] ?? "Workspace data";
  const failure = failureDetails(message);
  const [retrying, setRetrying] = useState(false);
  async function retry() {
    if (!onRetry || retrying) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  }
  return (
    <section role="alert" className="request-failure" aria-busy={retrying}>
      <div className="request-failure-icon">
        <CloudOff size={25} strokeWidth={1.5} aria-hidden="true" />
      </div>
      <div className="request-failure-body">
        <div className="request-failure-eyebrow">{area}</div>
        <h2>
          {title ??
            (action
              ? "This action could not be confirmed"
              : `${area} could not be loaded`)}
        </h2>
        <p>{failure.description}</p>
        <div className="request-failure-status">
          <span />
          {failure.label}
          {hasData && <small>Showing the last loaded data</small>}
        </div>
        {action && (
          <p className="request-failure-note">
            Your entries are still here. Check the latest result before
            submitting again.
          </p>
        )}
        <div className="request-failure-actions">
          {onRetry && (
            <button type="button" onClick={retry} disabled={retrying}>
              <RefreshCw size={14} className={retrying ? "animate-spin" : ""} />
              {retrying ? "Reconnecting..." : "Try again"}
            </button>
          )}
          <Link href="/">
            Back to dashboard <ArrowUpRight size={14} />
          </Link>
        </div>
        <details className="request-failure-details">
          <summary>
            <Info size={12} /> Connection details
          </summary>
          <dl>
            <div>
              <dt>Area</dt>
              <dd>{area}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                {failure.status ? `HTTP ${failure.status}` : failure.label}
              </dd>
            </div>
            {failure.code && (
              <div>
                <dt>Reference</dt>
                <dd>{failure.code}</dd>
              </div>
            )}
            <div>
              <dt>Service message</dt>
              <dd>
                {failure.technical || "No additional details were returned."}
              </dd>
            </div>
          </dl>
        </details>
      </div>
    </section>
  );
}
