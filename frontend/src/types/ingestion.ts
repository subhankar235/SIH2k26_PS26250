export interface StreamStatus {
  topic: string;
  status: "active" | "lagging" | "error";
  rate: string;
  lag: number;
  errorCount: number;
}

export interface FlaggedRecord {
  id: string;
  source: string;
  time: string;
  reason: string;
  status: "Invalid" | "Stale" | "Conflict" | "Valid";
  version: number;
  duplicate: boolean;
  value?: number;
}
