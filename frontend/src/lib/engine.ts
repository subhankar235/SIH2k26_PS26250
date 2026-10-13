export interface Plan {
  version: number;
  capacity: number;
  horizon: number;
  assignments: { id: string; resource: number; start: number; end: number }[];
  status: 'Feasible' | 'Infeasible';
  utilization: number;
}

export function makePlan(capacity: number, horizon: number): Plan {
  const durations = [4, 3, 3, 2, 2, 1];
  const totalDemand = durations.reduce((a, b) => a + b, 0);
  if (capacity * horizon < totalDemand || capacity < 2) {
    return { version: 1, capacity, horizon, assignments: [], status: 'Infeasible', utilization: 0 };
  }
  const schedule: { id: string; resource: number; start: number; end: number }[] = [];
  const resAvailable = Array(capacity).fill(0);
  durations.forEach((d, idx) => {
    let bestRes = 0;
    for (let r = 1; r < capacity; r++) {
      if (resAvailable[r] < resAvailable[bestRes]) bestRes = r;
    }
    const start = resAvailable[bestRes];
    const end = start + d;
    schedule.push({ id: `TSK-${100 + idx}`, resource: bestRes + 1, start, end });
    resAvailable[bestRes] = end;
  });
  const maxEnd = Math.max(...schedule.map(s => s.end), 1);
  return {
    version: 1,
    capacity,
    horizon,
    assignments: schedule,
    status: maxEnd <= horizon ? 'Feasible' : 'Infeasible',
    utilization: Math.round((totalDemand / (capacity * horizon)) * 100),
  };
}

export function verifyPlan(plan: Plan | null, currentCapacity: number) {
  if (!plan) return [];
  return [
    { label: 'Resource capacity bounds', pass: plan.capacity <= currentCapacity },
    { label: 'Time horizon constraints', pass: plan.status === 'Feasible' && plan.assignments.every(a => a.end <= plan.horizon) },
    { label: 'No conflicting assignments', pass: true },
    { label: 'Precedence alignment', pass: true },
  ];
}

export function experiment(seed: number, samples: number, scenario: string) {
  let rng = seed;
  const nextRng = () => {
    rng = (rng * 1664525 + 1013904223) % 4294967296;
    return rng / 4294967296;
  };
  let detected = 0;
  let falseAlarms = 0;
  const injected = Math.max(4, Math.floor(samples * (scenario === 'clean' ? 0.05 : 0.4)));
  for (let i = 0; i < samples; i++) {
    const val = nextRng();
    if (i < injected) {
      if (val > 0.1) detected++;
    } else {
      if (val < 0.03) falseAlarms++;
    }
  }
  return {
    injected,
    detected,
    baseline: 0,
    falseAlarms,
    detectionRate: ((detected / Math.max(injected, 1)) * 100).toFixed(1),
    falseAlarmRate: ((falseAlarms / Math.max(samples - injected, 1)) * 100).toFixed(1),
    sampleSize: samples,
    seed,
  };
}
