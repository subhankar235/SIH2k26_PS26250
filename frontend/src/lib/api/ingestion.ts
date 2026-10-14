import { api } from "./client";
import type { StreamStatus, FlaggedRecord } from "@/types/ingestion";

export async function getIngestionStatus(): Promise<StreamStatus[]> {
  return await api<StreamStatus[]>("/ingestion/status");
}

export async function getFlaggedRecords(): Promise<FlaggedRecord[]> {
  return await api<FlaggedRecord[]>("/ingestion/flagged");
}
