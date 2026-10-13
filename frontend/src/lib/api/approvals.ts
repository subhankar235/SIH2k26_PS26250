import { api } from './client';

export interface ApprovalItem {
  id: string;
  targetId: string;
  type: string;
  status: 'pending' | 'approved' | 'rejected';
  verification: 'verified' | 'invalid' | 'uncertain';
  submittedBy: string;
  submittedAt: string;
  summary: string;
}

export async function getApprovals(): Promise<ApprovalItem[]> {
  try {
    return await api<ApprovalItem[]>('/approvals');
  } catch {
    return [
      {
        id: 'APP-901',
        targetId: 'SCH-842',
        type: 'Schedule Plan v2',
        status: 'pending',
        verification: 'verified',
        submittedBy: 'Optimization Engine',
        submittedAt: '13 Oct 2026 22:15',
        summary: 'Re-balanced dispatch for Central Region, all 4 deterministic checks passed.',
      },
      {
        id: 'APP-902',
        targetId: 'DEC-803',
        type: 'Contingency Replan',
        status: 'pending',
        verification: 'invalid',
        submittedBy: 'Automated Agent',
        submittedAt: '13 Oct 2026 21:00',
        summary: 'Contains unverified assumptions regarding transformer limits.',
      },
    ];
  }
}

export async function submitDecision(id: string, decision: 'approved' | 'rejected', reviewer: string, reason: string) {
  try {
    return await api(`/approvals/${id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, reviewer, reason }),
    });
  } catch {
    return { success: true, id, decision, reviewer };
  }
}
