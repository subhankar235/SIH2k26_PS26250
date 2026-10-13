export interface Assignment {
  taskId: string;
  resourceId: string;
  start: number;
  end: number;
}

export interface Schedule {
  id: string;
  version: number;
  assignments: Assignment[];
  objectives: Record<string, number>;
  verification: "verified" | "invalid" | "uncertain";
  status?: "feasible" | "infeasible" | "optimal";
  capacity?: number;
  horizon?: number;
}

export interface ScheduleDiff {
  added: Assignment[];
  removed: Assignment[];
  moved: { before: Assignment; after: Assignment }[];
  unchanged: number;
}
