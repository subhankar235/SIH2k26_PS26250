import { api } from "./client";

export interface VerificationRequest {
  target_type: string;
  target_id: string;
}

export interface Violation {
  rule: string;
  message: string;
  refs: string[];
}

export interface VerificationResult {
  outcome: "verified" | "invalid" | "uncertain";
  violations: Violation[];
  uncertainty_flags: string[];
}

export function checkVerification(
  request: VerificationRequest,
): Promise<VerificationResult> {
  return api<VerificationResult>("/verification/check", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getVerification(id: string): Promise<VerificationResult> {
  return api<VerificationResult>(`/verification/${encodeURIComponent(id)}`);
}
