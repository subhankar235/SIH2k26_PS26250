import { api } from "./client";
import type { Forecast } from "@/types/forecast";

export async function getForecast(id = "FORECAST-01"): Promise<Forecast> {
  return await api<Forecast>(`/forecasts/${encodeURIComponent(id)}`);
}
