export type IssueClass = "stale" | "missing" | "duplicate" | "conflict";

export interface Claim {
  id: string;
  attribute: string;
  value: string;
  sourceId: string;
  observedAt: string;
  supersededBy?: string | null;
}

export interface Autopsy {
  issueId: string;
  issueClass: IssueClass;
  claims: Claim[];
  provenance: { step: string; at: string; sourceId: string }[];
  missingInformation: string[];
  uncertainty: { label: string; value: number }[];
}

export interface EvidenceIssue {
  id: string;
  issueClass: IssueClass;
  status: "open" | "resolved";
  sourceId: string;
  detectedAt: string;
  affectedResource: string;
  details?: Record<string, unknown>;
}
