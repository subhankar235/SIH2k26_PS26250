export interface Assignment {
  taskId: string;
  resourceId: string;
  start: number;
  end: number;
  crewId?: string;
  corridorId?: string;
  missionId?: string;
}

export interface Schedule {
  id: string;
  version: number;
  assignments: Assignment[];
  objectives: Record<string, number>;
  verification: "verified" | "invalid" | "uncertain";
}

export interface ScheduleDiff {
  added: Assignment[];
  removed: Assignment[];
  moved: { before: Assignment; after: Assignment }[];
  unchanged: number;
}
