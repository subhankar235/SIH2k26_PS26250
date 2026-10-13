export interface BenchmarkResult {
  metric: string;
  system: number;
  baseline: number;
  effectSize: string;
  pValue: number;
  ci: [number, number];
}

export interface Ablation {
  name: string;
  accuracy: string;
  recoveryTime: string;
  feasibility: string;
}
