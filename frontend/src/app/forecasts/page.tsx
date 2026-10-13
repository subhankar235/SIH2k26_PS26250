'use client';
import React, { useState } from 'react';
import { PageHeader } from '@/components/layout';
import { Card, CardHeader, CardContent, Badge } from '@/components/ui';
import { UncertaintyBandChart, CalibrationPlot } from '@/components/charts';
import { AlertTriangle, TrendingUp } from 'lucide-react';
import { MOCK_FORECAST_POINTS } from '@/lib/fixtures';

export default function ForecastsPage() {
  const [target, setTarget] = useState('Resource Demand');

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="FEATURE F4"
        title="Probabilistic Forecasting & Uncertainty Bands"
        description="Bayesian deep state-space models output mean predictions alongside calibrated 90% prediction intervals."
      />

      {/* Target Selector */}
      <div className="flex items-center gap-4 bg-slate-900 border border-slate-800 p-3 rounded">
        <label className="text-xs text-slate-400 font-medium">Select Forecast Target:</label>
        {['Resource Demand', 'Resource Availability'].map(tg => (
          <button
            key={tg}
            onClick={() => setTarget(tg)}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              target === tg ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {tg}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <Badge tone="blue">DS-DGP Model v2</Badge>
          <Badge tone="green">Calibration: 89.4% (Nominal 90%)</Badge>
        </div>
      </div>

      {/* Main Chart Panel */}
      <Card>
        <CardHeader
          title={`${target} Horizon & 90% Uncertainty Band`}
          subtitle="Solid Line = Mean Forecast · Shaded Band = 90% Confidence Interval · Green Points = Observed Values"
        />
        <CardContent>
          <UncertaintyBandChart data={MOCK_FORECAST_POINTS} />
        </CardContent>
      </Card>

      {/* Calibration Plot & Warning */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Empirical Coverage Calibration" subtitle="Reliability diagram showing nominal vs empirical coverage" />
          <CardContent>
            <CalibrationPlot />
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="Operational Decision Guidelines" subtitle="Guidance for planners using predicted capacity" />
          <CardContent className="space-y-3 text-xs text-slate-300 leading-relaxed">
            <div className="p-3 bg-amber-950/30 border border-amber-900/60 rounded flex items-start gap-2.5 text-amber-300">
              <AlertTriangle size={16} className="text-amber-400 flex-shrink-0 mt-0.5" />
              <span>Do not treat predicted availability as confirmed capacity. Downstream scheduling strictly requires deterministic reserves when uncertainty bounds exceed 15%.</span>
            </div>
            <p>1. Uncertainty width naturally expands as the forecasting horizon extends from T+4h to T+24h.</p>
            <p>2. Sensor outages or missing telemetry automatically widen interval bounds to prevent overconfident allocations.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
