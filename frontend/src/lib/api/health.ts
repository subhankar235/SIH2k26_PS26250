import { getDataMode } from "@/lib/data-mode";
export interface Health {
  status: string;
  service: string;
}
export async function getHealth(): Promise<Health> {
  if (getDataMode() === "demo") {
    const { demoRequest } = await import("../demo-api");
    return (await demoRequest("/health")) as Health;
  }
  const base =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  const res = await fetch(new URL("/health", base), { cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json() as Promise<Health>;
}
