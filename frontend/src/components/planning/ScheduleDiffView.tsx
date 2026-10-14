import React from "react";
import {
  Card,
  CardHeader,
  CardContent,
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableCell,
  Badge,
} from "@/components/ui";
import { ScheduleDiff } from "@/types/schedule";

export function ScheduleDiffView({ diff }: { diff: ScheduleDiff }) {
  return (
    <Card>
      <CardHeader
        title="Schedule Diff Analysis"
        subtitle="Comparison between baseline and replanned schedule"
      />
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div className="p-3 bg-emerald-950/30 border border-emerald-900/40 rounded">
            <span className="text-xs text-emerald-400 font-medium">Added</span>
            <p className="text-lg font-bold text-emerald-200">
              {diff.added.length}
            </p>
          </div>
          <div className="p-3 bg-rose-950/30 border border-rose-900/40 rounded">
            <span className="text-xs text-rose-400 font-medium">Removed</span>
            <p className="text-lg font-bold text-rose-200">
              {diff.removed.length}
            </p>
          </div>
          <div className="p-3 bg-amber-950/30 border border-amber-900/40 rounded">
            <span className="text-xs text-amber-400 font-medium">Moved</span>
            <p className="text-lg font-bold text-amber-200">
              {diff.moved.length}
            </p>
          </div>
          <div className="p-3 bg-slate-800/40 border border-slate-700/40 rounded">
            <span className="text-xs text-slate-400 font-medium">
              Unchanged
            </span>
            <p className="text-lg font-bold text-slate-200">{diff.unchanged}</p>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Task ID</TableHead>
              <TableHead>Change Type</TableHead>
              <TableHead>Previous Window</TableHead>
              <TableHead>New Window</TableHead>
            </TableRow>
          </TableHeader>
          <tbody>
            {diff.added.map((a) => (
              <TableRow key={a.taskId}>
                <TableCell className="font-mono text-emerald-300">
                  {a.taskId}
                </TableCell>
                <TableCell>
                  <Badge tone="green">Added</Badge>
                </TableCell>
                <TableCell className="text-slate-500">—</TableCell>
                <TableCell className="font-mono text-slate-300">
                  T+{a.start}h → T+{a.end}h ({a.resourceId})
                </TableCell>
              </TableRow>
            ))}
            {diff.removed.map((r) => (
              <TableRow key={r.taskId}>
                <TableCell className="font-mono text-rose-300">
                  {r.taskId}
                </TableCell>
                <TableCell>
                  <Badge tone="red">Removed</Badge>
                </TableCell>
                <TableCell className="font-mono text-slate-300">
                  T+{r.start}h → T+{r.end}h ({r.resourceId})
                </TableCell>
                <TableCell className="text-slate-500">—</TableCell>
              </TableRow>
            ))}
            {diff.moved.map((m) => (
              <TableRow key={m.before.taskId}>
                <TableCell className="font-mono text-amber-300">
                  {m.before.taskId}
                </TableCell>
                <TableCell>
                  <Badge tone="amber">Moved</Badge>
                </TableCell>
                <TableCell className="font-mono text-slate-400">
                  T+{m.before.start}h → T+{m.before.end}h
                </TableCell>
                <TableCell className="font-mono text-slate-200">
                  T+{m.after.start}h → T+{m.after.end}h ({m.after.resourceId})
                </TableCell>
              </TableRow>
            ))}
          </tbody>
        </Table>
      </CardContent>
    </Card>
  );
}
