import { api } from './client';
import { EvidenceIssue, Autopsy } from '@/types/evidence';
import { MOCK_ISSUES } from '@/lib/fixtures';

export async function getIssues(): Promise<EvidenceIssue[]> {
  try {
    return await api<EvidenceIssue[]>('/evidence/issues');
  } catch {
    return MOCK_ISSUES;
  }
}

export async function getAutopsy(id: string): Promise<Autopsy> {
  try {
    return await api<Autopsy>(`/evidence/issues/${id}/autopsy`);
  } catch {
    return {
      issueId: id,
      issueClass: 'conflict',
      claims: [
        { id: 'CLM-01', attribute: 'available_units', value: '12 units', sourceId: 'SRC-001 (Registry)', observedAt: '09:40 UTC' },
        { id: 'CLM-02', attribute: 'available_units', value: '8 units', sourceId: 'SRC-002 (Telemetry)', observedAt: '09:43 UTC' },
      ],
      provenance: [
        { step: 'Ingestion validated via schema v1', at: '09:40 UTC', sourceId: 'SRC-001' },
        { step: 'Contradictory claim introduced', at: '09:43 UTC', sourceId: 'SRC-002' },
        { step: 'Linked to affected schedule SCH-024', at: '09:44 UTC', sourceId: 'Engine' },
      ],
      missingInformation: ['Physical meter reconciliation signature', 'Asset gateway heartbeat log'],
      uncertainty: [
        { label: 'Sensor noise estimate', value: 0.14 },
        { label: 'Transmission delay probability', value: 0.32 },
      ],
    };
  }
}
