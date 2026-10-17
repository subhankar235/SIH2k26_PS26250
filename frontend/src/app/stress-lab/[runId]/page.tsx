"use client";
import { use, useEffect } from "react";
import { PageHeader } from "@/components/layout";
import { Card, CardHeader, CardContent } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { MetricBarChart } from "@/components/charts";
import { usePolling } from "@/hooks/usePolling";
import { getStressRunById } from "@/lib/api/stress";
export default function StressRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  return <Run key={runId} id={runId} />;
}
function Run({ id }: { id: string }) {
  const request = usePolling(() => getStressRunById(id), 1500);
  const run = request.data;
  useEffect(() => {
    if (run && run.status !== "running") request.stop();
  }, [run, request.stop]);
  return (
    <div className="space-y-6">
      <PageHeader
        title={`Stress run: ${id}`}
        description="Status updates automatically while the run is active."
      />
      <LoadState {...request} resource="Stress run status" />
      {run && (
        <>
          <p role="status">
            Status: {run.status} &middot; Scenario: {run.scenario} &middot;
            Seed: {run.seed}
          </p>
          {run.status === "completed" && (
            <>
              <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
                {[
                  ["Detection rate", `${run.detectionRate}%`],
                  ["False alarms", run.falseAlarms],
                  ["Failure rate", `${run.failureRate}%`],
                  ["Feasibility", `${run.feasibility}%`],
                  ["Recovery time", `${run.recoveryTime}s`],
                ].map(([label, value]) => (
                  <Card key={label}>
                    <CardContent className="p-4">
                      <p className="text-sm text-slate-400">{label}</p>
                      <p className="font-mono text-xl">{value}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <Card>
                <CardHeader
                  title="Recovery time vs baseline"
                  subtitle="Seconds; lower is better"
                />
                <CardContent>
                  <MetricBarChart
                    data={[
                      {
                        metric: "Recovery time (s)",
                        system: run.recoveryTime,
                        baseline: run.baseline,
                      },
                    ]}
                  />
                </CardContent>
              </Card>
            </>
          )}
          {run.status === "failed" && (
            <p role="alert">
              The experiment failed. Return to the stress lab to launch another
              run.
            </p>
          )}
        </>
      )}
    </div>
  );
}
