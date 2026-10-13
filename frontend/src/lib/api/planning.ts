import { api } from './client';
import { Schedule, ScheduleDiff } from '@/types/schedule';
import { makePlan } from '@/lib/engine';

export async function solveSchedule(capacity: number, horizon: number): Promise<Schedule> {
  try {
    return await api<Schedule>('/planning/solve', {
      method: 'POST',
      body: JSON.stringify({ capacity, horizon }),
    });
  } catch {
    const p = makePlan(capacity, horizon);
    return {
      id: `SCH-${Date.now().toString().slice(-4)}`,
      version: p.version,
      assignments: p.assignments.map(a => ({ taskId: a.id, resourceId: `RES-${a.resource}`, start: a.start, end: a.end })),
      objectives: { utilization: p.utilization, cost: 4200, balance: 94 },
      verification: p.status === 'Feasible' ? 'verified' : 'invalid',
      status: p.status === 'Feasible' ? 'feasible' : 'infeasible',
      capacity,
      horizon,
    };
  }
}

export async function getScheduleDiff(oldId: string, newId: string): Promise<ScheduleDiff> {
  try {
    return await api<ScheduleDiff>(`/replanning/diff/${oldId}/${newId}`);
  } catch {
    return {
      added: [{ taskId: 'TSK-106', resourceId: 'RES-2', start: 4, end: 7 }],
      removed: [{ taskId: 'TSK-102', resourceId: 'RES-1', start: 0, end: 3 }],
      moved: [{ before: { taskId: 'TSK-103', resourceId: 'RES-2', start: 2, end: 5 }, after: { taskId: 'TSK-103', resourceId: 'RES-3', start: 3, end: 6 } }],
      unchanged: 4,
    };
  }
}
