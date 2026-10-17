"use client";
import React from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { ForecastPoint } from "@/types/forecast";

export function UncertaintyBandChart({ data }: { data: ForecastPoint[] }) {
  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data.map((point) => ({
            ...point,
            band: [point.lower, point.upper],
          }))}
          margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="bandGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#326d5d" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#326d5d" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#eaf0ec" strokeDasharray="3 3" />
          <XAxis dataKey="t" stroke="#88958c" fontSize={11} />
          <YAxis stroke="#88958c" fontSize={11} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              borderColor: "#dce7df",
              fontSize: "12px",
              borderRadius: "4px",
            }}
          />
          <Area
            type="monotone"
            dataKey="band"
            stroke="none"
            fill="url(#bandGradient)"
            name="Prediction interval"
          />
          {/* Mean prediction */}
          <Line
            type="monotone"
            dataKey="mean"
            stroke="#326d5d"
            strokeWidth={2}
            dot={false}
            name="Forecast Mean"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
