import type { ValidityStatus } from "@/types/validity";
const STYLES: Record<ValidityStatus, string> = {
  verified: "bg-green-100 text-green-800",
  stale: "bg-yellow-100 text-yellow-800",
  invalidated: "bg-red-100 text-red-800",
  uncertain: "bg-gray-200 text-gray-800",
};
export function ValidityBadge({ status }: { status: ValidityStatus }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
