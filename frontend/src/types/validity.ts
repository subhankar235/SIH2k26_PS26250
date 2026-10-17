export type ValidityStatus = "verified" | "stale" | "invalidated" | "uncertain";

export interface Assumption {
  id: string;
  description: string;
}

export interface Dependency {
  inputId: string;
  inputVersion: number;
}

export interface Decision {
  id: string;
  type: string;
  version: number;
  status: ValidityStatus;
  createdAt: string;
  assumptions: Assumption[];
  dependencies: Dependency[];
}
