import { api } from './client';
import { BenchmarkResult, Ablation } from '@/types/benchmark';
import { MOCK_BENCHMARKS, MOCK_ABLATIONS } from '@/lib/fixtures';

export async function getBenchmarkResults(): Promise<BenchmarkResult[]> {
  try {
    return await api<BenchmarkResult[]>('/benchmarks/results');
  } catch {
    return MOCK_BENCHMARKS;
  }
}

export async function getAblations(): Promise<Ablation[]> {
  try {
    return await api<Ablation[]>('/benchmarks/ablations');
  } catch {
    return MOCK_ABLATIONS;
  }
}
