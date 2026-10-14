import { Spinner } from "./Spinner";
import { ErrorState } from "./ErrorState";
import { EmptyState } from "./EmptyState";
import type { RequestFailure } from "@/lib/request-failure";
export function LoadState({
  loading,
  error,
  empty,
  refetch,
  resource,
  data,
  action = false,
}: {
  loading: boolean;
  error: RequestFailure | null;
  empty?: boolean;
  refetch?: () => void | Promise<void>;
  resource?: string;
  data?: unknown;
  action?: boolean;
}) {
  if (error)
    return (
      <ErrorState
        message={error}
        onRetry={refetch}
        resource={resource}
        hasData={data != null}
        action={action}
      />
    );
  if (loading)
    return (
      <div className="request-loading">
        <Spinner />
        <span>Loading {resource?.toLowerCase() ?? "the latest data"}...</span>
      </div>
    );
  if (empty)
    return (
      <EmptyState
        title={resource ? `No ${resource.toLowerCase()} to show` : "No results"}
        message="No records match this view. New records will appear here when they are available."
      />
    );
  return null;
}
