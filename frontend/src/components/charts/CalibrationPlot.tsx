"use client";
import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

export function CalibrationPlot({
  points,
}: {
  points: { nominal: number; empirical: number }[];
}) {
  if (!points.length)
    return (
      <p className="text-sm text-slate-400">
        No calibration measurements reported.
      </p>
    );

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#eaf0ec" strokeDasharray="3 3" />
          <XAxis dataKey="nominal" stroke="#88958c" fontSize={11} unit="%" />
          <YAxis stroke="#88958c" fontSize={11} unit="%" domain={[40, 100]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              borderColor: "#dce7df",
              fontSize: "12px",
            }}
          />
          <Legend wrapperStyle={{ fontSize: "12px" }} />
          <Line
            type="linear"
            dataKey="nominal"
            stroke="#88958c"
            strokeDasharray="4 4"
            dot={false}
            name="Ideal Calibration"
          />
          <Line
            type="monotone"
            dataKey="empirical"
            stroke="#79cfaa"
            strokeWidth={2}
            dot={{ r: 4 }}
            name="AERONIQ Model"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
