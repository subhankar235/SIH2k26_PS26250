export type ScenarioType = "clean" | "heavy_staleness" | "source_conflict" | "cascading_changes";
export type FaultSeverity = "low" | "medium" | "high";

export interface StressRun {
  id: string;
  scenario: ScenarioType;
  seed: number;
  faultSeverity: FaultSeverity;
  status: "running" | "completed" | "failed";
  detectionRate: number;
  falseAlarms: number;
  failureRate: number;
  feasibility: number;
  recoveryTime: number;
  baseline: number;
  createdAt: string;
}
