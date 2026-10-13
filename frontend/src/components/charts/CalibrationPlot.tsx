'use client';
import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts';

export function CalibrationPlot() {
  const points = [
    { nominal: 50, empirical: 51 },
    { nominal: 60, empirical: 59 },
    { nominal: 70, empirical: 71 },
    { nominal: 80, empirical: 79 },
    { nominal: 90, empirical: 89.4 },
    { nominal: 95, empirical: 94.2 },
  ];

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="nominal" stroke="#64748b" fontSize={11} unit="%" />
          <YAxis stroke="#64748b" fontSize={11} unit="%" domain={[40, 100]} />
          <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '12px' }} />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Line type="linear" dataKey="nominal" stroke="#64748b" strokeDasharray="4 4" dot={false} name="Ideal Calibration" />
          <Line type="monotone" dataKey="empirical" stroke="#10b981" strokeWidth={2} dot={{ r: 4 }} name="Air Power Model" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
