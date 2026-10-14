import { getDataMode } from "@/lib/data-mode";
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (getDataMode() === "demo") {
    const { demoRequest } = await import("../demo-api");
    return (await demoRequest(path, init)) as T;
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(0, "connection_unavailable", "Connection unavailable");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.code ?? "unknown",
      body?.message ?? res.statusText,
      body?.details,
    );
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(
      res.status,
      "invalid_response",
      "The service returned an unreadable response.",
    );
  }
}
