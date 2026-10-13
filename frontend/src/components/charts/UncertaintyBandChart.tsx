'use client';
import React from 'react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { ForecastPoint } from '@/types/forecast';

export function UncertaintyBandChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="bandGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="t" stroke="#64748b" fontSize={11} />
          <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']} />
          <Tooltip
            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px', borderRadius: '4px' }}
          />
          {/* Upper confidence bound */}
          <Area type="monotone" dataKey="upper" stroke="none" fill="url(#bandGradient)" />
          {/* Lower confidence mask */}
          <Area type="monotone" dataKey="lower" stroke="none" fill="#090d16" />
          {/* Mean prediction */}
          <Line type="monotone" dataKey="mean" stroke="#38bdf8" strokeWidth={2} dot={false} name="Forecast Mean" />
          {/* Actual observed points */}
          <Line type="monotone" dataKey="observed" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} name="Observed" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
