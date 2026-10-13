const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.code ?? "unknown", body.message ?? res.statusText, body.details);
    }
    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(503, "NETWORK_ERROR", (err as Error).message);
  }
}
