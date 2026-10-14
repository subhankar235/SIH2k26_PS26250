"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PageHeader } from "@/components/layout";
import { Button, Card, CardHeader, CardContent } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { useFetch } from "@/hooks/useFetch";
import { getStressRuns, launchStressRun } from "@/lib/api/stress";
import type { ScenarioType, FaultSeverity } from "@/types/stress";
export default function StressLabPage() {
  const router = useRouter();
  const request = useFetch(getStressRuns);
  const [scenario, setScenario] = useState<ScenarioType>("clean");
  const [seed, setSeed] = useState("42");
  const [severity, setSeverity] = useState<FaultSeverity>("medium");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | string | null>(null);
  async function launch(e: React.FormEvent) {
    e.preventDefault();
    if (!Number.isSafeInteger(Number(seed))) {
      setError("Enter an integer seed.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await launchStressRun(scenario, Number(seed), severity);
      router.push(`/stress-lab/${encodeURIComponent(run.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err : "Launch failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <PageHeader
        title="Stress lab"
        description="Run reproducible fault scenarios and measure recovery."
      />
      <form onSubmit={launch} className="flex flex-wrap gap-4 items-end">
        <label>
          Scenario
          <select
            className="block bg-slate-900 border border-slate-700 p-2 rounded"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as ScenarioType)}
          >
            {(
              [
                "clean",
                "heavy_staleness",
                "source_conflict",
                "cascading_changes",
              ] as const
            ).map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Seed
          <input
            type="number"
            required
            step="1"
            className="block bg-slate-900 border border-slate-700 p-2 rounded"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <label>
          Fault severity
          <select
            className="block bg-slate-900 border border-slate-700 p-2 rounded"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as FaultSeverity)}
          >
            {["low", "medium", "high"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <Button type="submit" loading={busy}>
          Launch stress run
        </Button>
      </form>
      <LoadState loading={false} error={error} action />
      <LoadState {...request} empty={request.data?.length === 0} />
      {request.data && request.data.length > 0 && (
        <>
          <Card>
            <CardHeader title="Run history" />
            <CardContent>
              <ul className="space-y-3">
                {request.data?.map((run) => (
                  <li key={run.id}>
                    <Link
                      className="text-sky-300"
                      href={`/stress-lab/${encodeURIComponent(run.id)}`}
                    >
                      {run.id}
                    </Link>{" "}
                    &middot; {run.scenario} &middot; Seed {run.seed} &middot;{" "}
                    {run.status}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
