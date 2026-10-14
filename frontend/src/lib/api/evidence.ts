import { api } from "./client";
import type { EvidenceIssue, Autopsy } from "@/types/evidence";

export async function getIssues(): Promise<EvidenceIssue[]> {
  return await api<EvidenceIssue[]>("/evidence/issues");
}

export async function getAutopsy(id: string): Promise<Autopsy> {
  return await api<Autopsy>(
    `/evidence/issues/${encodeURIComponent(id)}/autopsy`,
  );
}
