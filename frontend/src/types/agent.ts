export interface AgentRun {
  id: string;
  status: "running" | "completed" | "failed";
  query: string;
  nodesVisited: string[];
  retries: number;
  explanation: string;
  evidenceLinks: { id: string; label: string; version: number }[];
  createdAt: string;
}
