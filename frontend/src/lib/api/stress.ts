import { api } from "./client";
import type { StressRun, ScenarioType, FaultSeverity } from "@/types/stress";

export async function getStressRuns(): Promise<StressRun[]> {
  return await api<StressRun[]>("/stress/runs");
}

export async function getStressRunById(id: string): Promise<StressRun | null> {
  return await api<StressRun>(`/stress/runs/${encodeURIComponent(id)}`);
}

export async function launchStressRun(
  scenario: ScenarioType,
  seed: number,
  faultSeverity: FaultSeverity,
): Promise<StressRun> {
  return await api<StressRun>("/stress/runs", {
    method: "POST",
    body: JSON.stringify({ scenario, seed, faultSeverity }),
  });
}
