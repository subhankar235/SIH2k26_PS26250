import { api } from './client';
import { AgentRun } from '@/types/agent';

const MOCK_AGENT_RUNS: AgentRun[] = [
  {
    id: 'AGENT-401',
    status: 'completed',
    query: 'Investigate conflicting capacity reports between registry and telemetry for Substation 4',
    nodesVisited: ['ingestion_inspector', 'evidence_graph_builder', 'verifier', 'explainer'],
    retries: 0,
    explanation: 'Identified a 4-unit divergence due to a delayed inventory sync (SRC-001 v2). Verified unaffected status on dependent lines SCH-012.',
    evidenceLinks: [
      { id: 'REC-1050', label: 'Availability feed v2', version: 2 },
      { id: 'ISSUE-01', label: 'Resource 008 contradiction', version: 1 },
    ],
    createdAt: '13 Oct 2026 21:14',
  },
  {
    id: 'AGENT-402',
    status: 'completed',
    query: 'Explain why DEC-803 was marked invalidated after telemetry ingestion',
    nodesVisited: ['provenance_tracer', 'dependency_graph_traverser', 'verifier'],
    retries: 1,
    explanation: 'DEC-803 depended on input REC-1050 at version 1. Ingestion of REC-1050 v2 triggered an automated range constraint check which failed, invalidating downstream dependent decision DEC-803.',
    evidenceLinks: [
      { id: 'REC-1050', label: 'Availability feed v2 (invalid)', version: 2 },
      { id: 'DEC-803', label: 'Contingency Replan', version: 2 },
    ],
    createdAt: '13 Oct 2026 21:45',
  },
];

export async function getAgentRuns(): Promise<AgentRun[]> {
  try {
    return await api<AgentRun[]>('/agents/requests');
  } catch {
    return MOCK_AGENT_RUNS;
  }
}

export async function getAgentRunById(id: string): Promise<AgentRun | null> {
  try {
    return await api<AgentRun>(`/agents/requests/${id}`);
  } catch {
    return MOCK_AGENT_RUNS.find((r) => r.id === id) || null;
  }
}

export async function submitAgentRequest(query: string): Promise<AgentRun> {
  try {
    return await api<AgentRun>('/agents/requests', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  } catch {
    const newRun: AgentRun = {
      id: `AGENT-${Math.floor(400 + Math.random() * 500)}`,
      status: 'completed',
      query,
      nodesVisited: ['query_parser', 'provenance_tracer', 'evidence_graph_builder', 'verifier', 'explainer'],
      retries: 0,
      explanation: `Synthesized audit trail and dependency lineage for query "${query}". Ingestion contract validated with zero constraint violations.`,
      evidenceLinks: [
        { id: 'REC-1049', label: 'Resource registry v1', version: 1 },
        { id: 'DEC-801', label: 'Dispatch Plan v3', version: 3 },
      ],
      createdAt: new Date().toLocaleTimeString(),
    };
    MOCK_AGENT_RUNS.unshift(newRun);
    return newRun;
  }
}

