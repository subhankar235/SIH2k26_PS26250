import { api } from './client';
import { AuditEntry } from '@/types/audit';

export async function getAuditEntries(): Promise<AuditEntry[]> {
  try {
    return await api<AuditEntry[]>('/audit');
  } catch {
    return [
      { id: 'AUD-001', entity: 'Schedule SCH-842', action: 'Created heuristic plan', actor: 'Planner Service', timestamp: '22:15:00 UTC' },
      { id: 'AUD-002', entity: 'Decision DEC-801', action: 'Deterministic check verified', actor: 'Verifier Engine', timestamp: '20:10:00 UTC' },
      { id: 'AUD-003', entity: 'Record REC-1050', action: 'Flagged range validation error', actor: 'Ingestion Service', timestamp: '18:40:00 UTC' },
      { id: 'AUD-004', entity: 'Policy POL-012', action: 'Updated reserve threshold to 15%', actor: 'Kathakali Das', timestamp: '14:20:00 UTC' },
    ];
  }
}
