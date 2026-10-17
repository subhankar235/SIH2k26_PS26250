"use client";
import { useDataMode } from "@/lib/data-mode";
import { useFetch } from "@/hooks/useFetch";
import { useState } from "react";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { ScheduleDiffView } from "@/components/planning";
import { getScheduleDiff } from "@/lib/api/planning";
import type { ScheduleDiff } from "@/types/schedule";
export default function PlanningComparePage() {
  const { mode } = useDataMode();
  const example = useFetch(() =>
    mode === "demo"
      ? getScheduleDiff("SCH-841", "SCH-842")
      : Promise.resolve(null),
  );
  const [oldId, setOldId] = useState(mode === "demo" ? "SCH-841" : "");
  const [newId, setNewId] = useState(mode === "demo" ? "SCH-842" : "");
  const [comparedDiff, setDiff] = useState<ScheduleDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | string | null>(null);
  const diff = comparedDiff ?? (!loading && !error ? example.data : null);
  async function compare(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setDiff(null);
    try {
      setDiff(await getScheduleDiff(oldId.trim(), newId.trim()));
    } catch (err) {
      setError(err instanceof Error ? err : "Comparison failed");
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="space-y-6">
      <PageHeader
        title="Compare schedules"
        description="Inspect changed assignments and the impact of replanning."
      />
      <form onSubmit={compare} className="flex flex-wrap gap-4 items-end">
        <label>
          Original schedule
          <input
            required
            value={oldId}
            onChange={(e) => setOldId(e.target.value)}
            className="block bg-slate-900 border border-slate-700 p-2 rounded"
          />
        </label>
        <label>
          New schedule
          <input
            required
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            className="block bg-slate-900 border border-slate-700 p-2 rounded"
          />
        </label>
        <Button type="submit" loading={loading}>
          Compare
        </Button>
      </form>
      <LoadState loading={loading} error={error} action />
      {diff && (
        <>
          <p role="status">
            Change impact: {diff.added.length} added, {diff.removed.length}{" "}
            removed, {diff.moved.length} moved; {diff.unchanged} assignments
            unchanged.
          </p>
          <ScheduleDiffView diff={diff} />
        </>
      )}
    </div>
  );
}
