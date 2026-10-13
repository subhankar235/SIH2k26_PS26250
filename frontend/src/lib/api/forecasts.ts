import { api } from './client';
import { Forecast } from '@/types/forecast';
import { MOCK_FORECAST_POINTS } from '@/lib/fixtures';

export async function getForecast(id = 'FORECAST-01'): Promise<Forecast> {
  try {
    return await api<Forecast>(`/forecasts/${id}`);
  } catch {
    return {
      id,
      target: 'Grid Demand & Capacity Horizon',
      points: MOCK_FORECAST_POINTS,
      coverage: 89.4,
      highUncertainty: false,
      horizon: '24 Hours',
    };
  }
}
