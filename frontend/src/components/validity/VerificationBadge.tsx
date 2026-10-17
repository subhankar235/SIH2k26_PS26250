import type { Schedule } from "@/types/schedule";
export function VerificationBadge({
  status,
}: {
  status: Schedule["verification"];
}) {
  const style =
    status === "verified"
      ? "bg-green-100 text-green-800"
      : status === "invalid"
        ? "bg-red-100 text-red-800"
        : "bg-gray-200 text-gray-800";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
