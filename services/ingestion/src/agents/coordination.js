const SPECIALISTS = Object.freeze(['fleet', 'crew', 'weather', 'airport', 'cargo']);
const uniqueSorted = values => [...new Set(values)].sort();

// This is a deterministic trace of the finite solver's evidence flow. Its
// messages do not run tools, negotiate with an LLM or alter the verified plan.
export function buildReliefCoordination(world, plan, validation) {
  if (validation?.valid !== true || !Array.isArray(validation.errors) || validation.errors.length) {
    throw new TypeError('Coordination requires a verified relief plan');
  }
  const entities = new Set(['aircraft', 'crews', 'airports', 'requests'].flatMap(key => world[key].map(value => value.id)));
  if (!Array.isArray(plan.agentReports) || plan.agentReports.length !== SPECIALISTS.length ||
      plan.agentReports.some((report, index) => report.agentId !== SPECIALISTS[index] || !Array.isArray(report.findings))) {
    throw new TypeError('Invalid specialist evidence');
  }
  const findings = plan.agentReports.flatMap(report => report.findings);
  if (new Set(findings.map(finding => finding.id)).size !== findings.length || findings.some(finding =>
    typeof finding.id !== 'string' || !Array.isArray(finding.entityIds) || finding.entityIds.some(id => !entities.has(id)))) {
    throw new TypeError('Invalid specialist evidence references');
  }
  if (!Array.isArray(plan.assignments) || plan.assignments.length > 5 || plan.assignments.some(assignment =>
    !world.requests.some(request => request.id === assignment.requestId) ||
    !world.aircraft.some(aircraft => aircraft.id === assignment.aircraftId) ||
    !world.crews.some(crew => crew.id === assignment.crewId))) {
    throw new TypeError('Invalid assignment evidence references');
  }
  const priority = plan.assignments.reduce((sum, assignment) => sum + world.requests.find(request => request.id === assignment.requestId).priority, 0);
  if (plan.objective?.servedPriority !== priority) throw new TypeError('Coordination requires a verified objective');
  const messages = plan.agentReports.map(report => {
    const blocked = report.findings.filter(finding => finding.code !== 'ELIGIBLE').length;
    return {
      id: `SIM-MSG-${world.revision}-${report.agentId}`, from: report.agentId, to: 'supervisor', kind: 'evidence',
      entityIds: uniqueSorted(report.findings.flatMap(finding => finding.entityIds)),
      findingIds: uniqueSorted(report.findings.map(finding => finding.id)),
      summary: `${report.agentId} supplied ${report.findings.length} findings, including ${blocked} blocking findings, for the fixed scenario checks.`,
    };
  });
  messages.push({
    id: `SIM-MSG-${world.revision}-supervisor`, from: 'supervisor', to: 'all', kind: 'resolution',
    entityIds: uniqueSorted(plan.assignments.flatMap(assignment => [assignment.requestId, assignment.aircraftId, assignment.crewId])),
    findingIds: uniqueSorted(findings.map(finding => finding.id)),
    summary: `The supervisor selected ${plan.assignments.length} assignments with served priority ${plan.objective.servedPriority}; the independent checker verified feasibility and objective arithmetic.`,
  });
  return { version: 1, topology: 'specialists-supervisor', messages,
    decision: { status: 'verified', servedPriority: plan.objective.servedPriority, assignedCount: plan.assignments.length } };
}
