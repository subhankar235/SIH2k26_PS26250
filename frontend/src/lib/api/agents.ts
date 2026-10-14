import { api } from "./client";
import type { AgentRun } from "@/types/agent";

export async function getAgentRuns(): Promise<AgentRun[]> {
  return await api<AgentRun[]>("/agents/requests");
}

export async function getAgentRunById(id: string): Promise<AgentRun | null> {
  return await api<AgentRun>(`/agents/requests/${encodeURIComponent(id)}`);
}

export async function submitAgentRequest(query: string): Promise<AgentRun> {
  return await api<AgentRun>("/agents/requests", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}
