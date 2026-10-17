import { api } from "./client";

export interface ApprovalItem {
  id: string;
  targetId: string;
  type: string;
  status: "pending" | "approved" | "rejected";
  verification: "verified" | "invalid" | "uncertain";
  submittedBy: string;
  submittedAt: string;
  summary: string;
}

export function getApprovals(): Promise<ApprovalItem[]> {
  return api<ApprovalItem[]>("/approvals");
}
export function submitDecision(
  id: string,
  decision: "approved" | "rejected",
  reviewer: string,
  rationale: string,
): Promise<ApprovalItem> {
  return api<ApprovalItem>(`/approvals/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, reviewer, rationale }),
  });
}
