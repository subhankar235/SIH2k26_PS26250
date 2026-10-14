"use client";
import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

export function MetricBarChart({
  data,
}: {
  data: { metric: string; system: number; baseline: number }[];
}) {
  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 10, right: 20, left: 0, bottom: 20 }}
        >
          <CartesianGrid stroke="#eaf0ec" strokeDasharray="3 3" />
          <XAxis
            dataKey="metric"
            stroke="#88958c"
            fontSize={11}
            interval={0}
            angle={-15}
            textAnchor="end"
          />
          <YAxis stroke="#88958c" fontSize={11} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#ffffff",
              borderColor: "#dce7df",
              fontSize: "12px",
              borderRadius: "4px",
            }}
          />
          <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }} />
          <Bar
            dataKey="system"
            fill="#326d5d"
            name="AERONIQ System"
            radius={[3, 3, 0, 0]}
          />
          <Bar
            dataKey="baseline"
            fill="#88958c"
            name="Baseline Heuristic"
            radius={[3, 3, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
