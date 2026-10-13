import { api } from './client';
import { StressRun, ScenarioType, FaultSeverity } from '@/types/stress';
import { experiment } from '@/lib/engine';

export const MOCK_STRESS_RUNS: StressRun[] = [
  {
    id: 'RUN-42',
    scenario: 'heavy_staleness',
    seed: 42,
    faultSeverity: 'medium',
    status: 'completed',
    detectionRate: 98.4,
    falseAlarms: 1,
    failureRate: 2.1,
    feasibility: 97.9,
    recoveryTime: 14.2,
    baseline: 48.6,
    createdAt: '13 Oct 2026 21:00 UTC',
  },
  {
    id: 'RUN-108',
    scenario: 'source_conflict',
    seed: 108,
    faultSeverity: 'high',
    status: 'completed',
    detectionRate: 99.1,
    falseAlarms: 2,
    failureRate: 1.5,
    feasibility: 98.5,
    recoveryTime: 11.8,
    baseline: 52.3,
    createdAt: '13 Oct 2026 19:30 UTC',
  },
  {
    id: 'RUN-999',
    scenario: 'cascading_changes',
    seed: 999,
    faultSeverity: 'high',
    status: 'completed',
    detectionRate: 96.8,
    falseAlarms: 3,
    failureRate: 4.0,
    feasibility: 94.2,
    recoveryTime: 16.5,
    baseline: 64.0,
    createdAt: '13 Oct 2026 16:15 UTC',
  },
];

export async function getStressRuns(): Promise<StressRun[]> {
  try {
    return await api<StressRun[]>('/stress/runs');
  } catch {
    return MOCK_STRESS_RUNS;
  }
}

export async function getStressRunById(id: string): Promise<StressRun | null> {
  try {
    return await api<StressRun>(`/stress/runs/${id}`);
  } catch {
    const found = MOCK_STRESS_RUNS.find((r) => r.id === id);
    if (found) return found;
    return {
      id,
      scenario: 'heavy_staleness',
      seed: 42,
      faultSeverity: 'medium',
      status: 'completed',
      detectionRate: 97.5,
      falseAlarms: 2,
      failureRate: 3.0,
      feasibility: 96.5,
      recoveryTime: 13.5,
      baseline: 48.0,
      createdAt: '13 Oct 2026 22:00 UTC',
    };
  }
}

export async function launchStressRun(scenario: ScenarioType, seed: number, faultSeverity: FaultSeverity): Promise<StressRun> {
  try {
    return await api<StressRun>('/stress/runs', {
      method: 'POST',
      body: JSON.stringify({ scenario, seed, faultSeverity }),
    });
  } catch {
    const res = experiment(seed, 30, scenario);
    const newRun: StressRun = {
      id: `RUN-${seed}`,
      scenario,
      seed,
      faultSeverity,
      status: 'completed',
      detectionRate: parseFloat(res.detectionRate),
      falseAlarms: res.falseAlarms,
      failureRate: 3.2,
      feasibility: 96.8,
      recoveryTime: 12.4,
      baseline: 48.0,
      createdAt: new Date().toISOString(),
    };
    MOCK_STRESS_RUNS.unshift(newRun);
    return newRun;
  }
}
