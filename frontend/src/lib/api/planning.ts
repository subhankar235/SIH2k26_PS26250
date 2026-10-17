import { api } from "./client";
import type { Schedule, ScheduleDiff } from "@/types/schedule";

export async function solveSchedule(
  capacity: number,
  horizon: number,
): Promise<Schedule> {
  return await api<Schedule>("/planning/solve", {
    method: "POST",
    body: JSON.stringify({ capacity, horizon }),
  });
}

export async function getScheduleDiff(
  oldId: string,
  newId: string,
): Promise<ScheduleDiff> {
  return await api<ScheduleDiff>(
    `/replanning/diff/${encodeURIComponent(oldId)}/${encodeURIComponent(newId)}`,
  );
}

export function getSchedule(id: string): Promise<Schedule> {
  return api<Schedule>(`/planning/schedules/${encodeURIComponent(id)}`);
}
export function getAlternatives(): Promise<Schedule[]> {
  return api<Schedule[]>("/planning/alternatives");
}
