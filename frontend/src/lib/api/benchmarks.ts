import { api } from "./client";
import type { BenchmarkResult, Ablation } from "@/types/benchmark";

export async function getBenchmarkResults(): Promise<BenchmarkResult[]> {
  return await api<BenchmarkResult[]>("/benchmarks/results");
}

export async function getAblations(): Promise<Ablation[]> {
  return await api<Ablation[]>("/benchmarks/ablations");
}
