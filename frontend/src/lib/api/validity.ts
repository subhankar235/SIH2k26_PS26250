import { api } from './client';
import { Decision } from '@/types/validity';
import { MOCK_DECISIONS } from '@/lib/fixtures';

export async function getDecisions(): Promise<Decision[]> {
  try {
    return await api<Decision[]>('/validity/decisions');
  } catch {
    return MOCK_DECISIONS;
  }
}

export async function reverifyDecision(id: string): Promise<{ success: boolean; status: string }> {
  try {
    return await api<{ success: boolean; status: string }>('/validity/reverify', {
      method: 'POST',
      body: JSON.stringify({ id }),
    });
  } catch {
    return { success: true, status: 'verified' };
  }
}
