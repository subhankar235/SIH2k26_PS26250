import { api } from "./client";
import type { AuditEntry } from "@/types/audit";
export function getAuditEntries(): Promise<AuditEntry[]> {
  return api<AuditEntry[]>("/audit");
}
