export const MOCK_STREAMS = [
  { topic: 'telemetry.assets', status: 'active' as const, rate: '1,420 msgs/s', lag: 12, errorCount: 0 },
  { topic: 'sensors.environmental', status: 'active' as const, rate: '850 msgs/s', lag: 45, errorCount: 2 },
  { topic: 'grid.dispatch', status: 'lagging' as const, rate: '320 msgs/s', lag: 280, errorCount: 5 },
  { topic: 'claims.external', status: 'active' as const, rate: '95 msgs/s', lag: 4, errorCount: 1 },
];

export const MOCK_RECORDS = [
  { id: 'REC-1051', source: 'Constraint service', time: '22:40:00', status: 'Valid' as const, version: 1, duplicate: false, reason: 'Passed contract check' },
  { id: 'REC-1050', source: 'Availability feed', time: '20:40:00', status: 'Invalid' as const, version: 2, duplicate: false, reason: 'Range validation failed' },
  { id: 'REC-1049', source: 'Resource registry', time: '18:40:00', status: 'Valid' as const, version: 1, duplicate: false, reason: 'Schema verified' },
  { id: 'REC-1048', source: 'Constraint service', time: '16:40:00', status: 'Valid' as const, version: 3, duplicate: true, reason: 'Duplicate payload suppressed' },
  { id: 'REC-1047', source: 'Availability feed', time: '14:40:00', status: 'Stale' as const, version: 1, duplicate: false, reason: 'TTL exceeded (>4h)' },
];

export const MOCK_ISSUES = [
  { id: 'ISSUE-01', issueClass: 'conflict' as const, status: 'open' as const, sourceId: 'SRC-001 vs SRC-002', detectedAt: '09:43 UTC', affectedResource: 'RESOURCE-008' },
  { id: 'ISSUE-02', issueClass: 'stale' as const, status: 'open' as const, sourceId: 'SRC-002', detectedAt: '08:15 UTC', affectedResource: 'RESOURCE-014' },
  { id: 'ISSUE-03', issueClass: 'duplicate' as const, status: 'resolved' as const, sourceId: 'SRC-001', detectedAt: '07:30 UTC', affectedResource: 'RESOURCE-021' },
  { id: 'ISSUE-04', issueClass: 'missing' as const, status: 'open' as const, sourceId: 'SRC-003', detectedAt: '06:00 UTC', affectedResource: 'RESOURCE-003' },
];

export const MOCK_DECISIONS = [
  {
    id: 'DEC-801',
    type: 'Dispatch Plan',
    version: 3,
    status: 'verified' as const,
    createdAt: '12 Oct 2026 14:00',
    assumptions: [{ id: 'A1', description: 'Transformer operating threshold < 85C' }, { id: 'A2', description: 'Reserve margin >= 15%' }],
    dependencies: [{ inputId: 'REC-1049', inputVersion: 1 }, { inputId: 'FORECAST-02', inputVersion: 3 }],
  },
  {
    id: 'DEC-802',
    type: 'Resource Allocation',
    version: 1,
    status: 'stale' as const,
    createdAt: '12 Oct 2026 11:20',
    assumptions: [{ id: 'A1', description: 'Fleet availability 92.9%' }],
    dependencies: [{ inputId: 'REC-1047', inputVersion: 1 }],
  },
  {
    id: 'DEC-803',
    type: 'Contingency Replan',
    version: 2,
    status: 'invalidated' as const,
    createdAt: '11 Oct 2026 19:45',
    assumptions: [{ id: 'A1', description: 'North Ridge line operational' }],
    dependencies: [{ inputId: 'REC-1050', inputVersion: 2 }],
  },
  {
    id: 'DEC-804',
    type: 'Load Forecast Policy',
    version: 1,
    status: 'uncertain' as const,
    createdAt: '11 Oct 2026 09:10',
    assumptions: [{ id: 'A1', description: 'External meteorological sensor uptime' }],
    dependencies: [{ inputId: 'REC-1048', inputVersion: 3 }],
  },
];

export const MOCK_FORECAST_POINTS = [
  { t: '00:00', mean: 1200, lower: 1100, upper: 1300, observed: 1210 },
  { t: '04:00', mean: 980, lower: 880, upper: 1080, observed: 995 },
  { t: '08:00', mean: 1450, lower: 1330, upper: 1570, observed: 1430 },
  { t: '12:00', mean: 1840, lower: 1690, upper: 1990, observed: 1845 },
  { t: '16:00', mean: 1920, lower: 1720, upper: 2120, observed: 1910 },
  { t: '20:00', mean: 1650, lower: 1420, upper: 1880 },
  { t: '24:00', mean: 1320, lower: 1050, upper: 1590 },
];

export const MOCK_BENCHMARKS = [
  { metric: 'Fault Detection Rate', system: 98.4, baseline: 74.2, effectSize: '+24.2%', pValue: 0.001, ci: [21.5, 26.9] as [number, number] },
  { metric: 'Mean False Alarm Rate', system: 1.8, baseline: 8.5, effectSize: '-6.7%', pValue: 0.002, ci: [-7.8, -5.6] as [number, number] },
  { metric: 'Recovery Time (s)', system: 14.2, baseline: 48.6, effectSize: '-34.4s', pValue: 0.001, ci: [-38.1, -30.7] as [number, number] },
  { metric: 'Schedule Feasibility (%)', system: 99.2, baseline: 83.1, effectSize: '+16.1%', pValue: 0.001, ci: [13.8, 18.4] as [number, number] },
];

export const MOCK_ABLATIONS = [
  { name: 'Full System (TGN + Ditto + CP-SAT)', accuracy: '98.4%', recoveryTime: '14.2s', feasibility: '99.2%' },
  { name: 'w/o Temporal Graph Network (TGN)', accuracy: '89.1%', recoveryTime: '26.4s', feasibility: '95.0%' },
  { name: 'w/o Ditto Entity Resolution', accuracy: '84.6%', recoveryTime: '31.2s', feasibility: '92.3%' },
  { name: 'w/o Uncertainty-Aware Constraints', accuracy: '91.2%', recoveryTime: '18.9s', feasibility: '86.4%' },
  { name: 'Baseline Heuristic Only', accuracy: '74.2%', recoveryTime: '48.6s', feasibility: '83.1%' },
];
