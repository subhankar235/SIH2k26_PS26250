"use client";
import { useState } from "react";
import { useDataMode } from "@/lib/data-mode";
import { PageHeader } from "@/components/layout";
import { Card, CardHeader, CardContent } from "@/components/ui";
import { LoadState } from "@/components/ui/LoadState";
import { UncertaintyBandChart, CalibrationPlot } from "@/components/charts";
import { useFetch } from "@/hooks/useFetch";
import { getForecast } from "@/lib/api/forecasts";
export default function ForecastsPage() {
  const { mode } = useDataMode();
  const [forecastId, setForecastId] = useState("FORECAST-01");
  const request = useFetch(() => getForecast(forecastId), [forecastId]);
  const forecast = request.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Forecasts & uncertainty"
        description="Mean predictions and 90% prediction intervals."
      />
      {mode === "demo" && (
        <label>
          Forecast scenario{" "}
          <select
            aria-label="Forecast scenario"
            value={forecastId}
            onChange={(e) => setForecastId(e.target.value)}
          >
            <option value="FORECAST-01">
              Resource demand - typical conditions
            </option>
            <option value="FORECAST-02">
              Reserve demand - high uncertainty
            </option>
          </select>
        </label>
      )}
      <LoadState {...request} />
      {forecast && (
        <>
          {forecast.highUncertainty && (
            <div
              role="alert"
              className="p-4 rounded bg-yellow-100 text-yellow-900"
            >
              High uncertainty: review the interval bounds before using this
              forecast for planning.
            </div>
          )}
          <Card>
            <CardHeader
              title={forecast.target}
              subtitle="Mean forecast with lower-to-upper prediction band"
            />
            <CardContent>
              <UncertaintyBandChart data={forecast.points} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader title="Forecast calibration" />
            <CardContent>
              {forecast.coverage === undefined ? (
                <p>Coverage has not been reported.</p>
              ) : (
                <>
                  <p>
                    Empirical coverage: {forecast.coverage}% &middot; Nominal:
                    90% &middot; Difference:{" "}
                    {(forecast.coverage - 90).toFixed(1)} percentage points
                  </p>
                  <CalibrationPlot
                    points={[{ nominal: 90, empirical: forecast.coverage }]}
                  />
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
