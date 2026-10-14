import Link from "next/link";
import type { Decision } from "@/types/validity";
import { Card, CardHeader, CardContent } from "@/components/ui";
export function DependencyGraphView({
  decision,
  title = "Input dependency graph",
}: {
  decision: Decision;
  title?: string;
}) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardContent>
        <ul className="space-y-3">
          {decision.dependencies.map((input) => (
            <li
              key={`${input.inputId}-${input.inputVersion}`}
              className="flex flex-wrap items-center gap-4 text-sm"
            >
              <Link
                className="border border-slate-700 p-3 rounded text-sky-300"
                href={`/evidence/${encodeURIComponent(input.inputId)}`}
              >
                {input.inputId} (v{input.inputVersion})
              </Link>
              <span aria-hidden="true">&rarr;</span>
              <span>
                {decision.id} (v{decision.version})
              </span>
            </li>
          ))}
        </ul>
        {!decision.dependencies.length && (
          <p>No input dependencies recorded.</p>
        )}
      </CardContent>
    </Card>
  );
}
