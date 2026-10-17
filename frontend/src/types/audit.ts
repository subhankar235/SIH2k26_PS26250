export interface AuditEntry {
  id: string;
  entity: string;
  action: string;
  actor: string;
  timestamp: string;
  details?: string;
  version?: number;
}
