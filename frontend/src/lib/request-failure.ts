export type RequestFailure = Error | string;
export function failureDetails(error: RequestFailure) {
  const message = typeof error === "string" ? error : error.message;
  const status =
    typeof error === "object" && "status" in error
      ? Number(error.status)
      : undefined;
  const code =
    typeof error === "object" && "code" in error
      ? String(error.code)
      : undefined;
  if (
    status === 0 ||
    /failed to fetch|networkerror|network request|load failed|connection unavailable/i.test(
      message,
    )
  ) {
    return {
      kind: "connection",
      label: "Connection unavailable",
      description:
        "We could not reach the data service. Check your connection and make sure the service is running, then try again.",
      status,
      code,
      technical: message,
    };
  }
  if (status === 404)
    return {
      kind: "missing",
      label: "Data not available",
      description:
        "The requested record or service endpoint could not be found. Check the record link, or try again once this service is available.",
      status,
      code,
      technical: message,
    };
  if (status === 401 || status === 403)
    return {
      kind: "access",
      label: "Access required",
      description:
        "Your current session does not have access to this data. Sign in with an authorized account or contact your workspace administrator.",
      status,
      code,
      technical: message,
    };
  if (status === 429)
    return {
      kind: "busy",
      label: "Too many requests",
      description:
        "The service is receiving too many requests. Wait a moment before trying again.",
      status,
      code,
      technical: message,
    };
  if (status && status >= 500)
    return {
      kind: "service",
      label: "Service temporarily unavailable",
      description:
        "The data service could not complete this request. Try again in a moment. If the problem continues, contact your workspace administrator.",
      status,
      code,
      technical: message,
    };
  if (status === 400 || status === 422)
    return {
      kind: "input",
      label: "Check the submitted details",
      description:
        "The service could not accept these values. Review the form details before submitting again.",
      status,
      code,
      technical: message,
    };
  return {
    kind: "request",
    label: "Request could not be completed",
    description:
      typeof error === "string"
        ? message
        : "We could not load the latest information. Try again, or return to the dashboard and open this view again.",
    status,
    code,
    technical: message,
  };
}
