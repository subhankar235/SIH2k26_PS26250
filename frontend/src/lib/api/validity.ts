import { api } from "./client";
import type { Decision } from "@/types/validity";

export async function getDecisions(): Promise<Decision[]> {
  return await api<Decision[]>("/validity/decisions");
}

export async function reverifyDecision(
  id: string,
): Promise<{ success: boolean; status: string }> {
  return await api<{ success: boolean; status: string }>("/validity/reverify", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export function getDecision(id: string): Promise<Decision> {
  return api<Decision>(`/validity/decisions/${encodeURIComponent(id)}`);
}
