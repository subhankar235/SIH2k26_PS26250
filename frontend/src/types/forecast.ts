export interface ForecastPoint {
  t: string;
  mean: number;
  lower: number;
  upper: number;
}

export interface Forecast {
  id: string;
  target: string;
  points: ForecastPoint[];
  coverage?: number;
  highUncertainty: boolean;
}
