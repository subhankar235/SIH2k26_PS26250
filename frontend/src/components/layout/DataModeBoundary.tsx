"use client";
import type { ReactNode } from "react";
import { useDataMode } from "@/lib/data-mode";
export function DataModeBoundary({ children }: { children: ReactNode }) {
  const { key, mode } = useDataMode();
  return (
    <div key={key}>
      {mode === "demo" && (
        <div className="demo-workspace-note">
          <span className="connection-dot" /> Demo workspace. All data and
          actions are simulated and saved only in this browser.
        </div>
      )}
      {children}
    </div>
  );
}
