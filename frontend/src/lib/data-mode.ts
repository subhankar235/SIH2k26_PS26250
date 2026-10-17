"use client";
import { useSyncExternalStore } from "react";
export type DataMode = "demo" | "live";
export const DEMO_STORAGE_KEY = "air-power-demo-v1";
const MODE_KEY = "air-power-data-mode";
const EVENT = "air-power-data-mode-change";
let fallback: DataMode = "demo";
let revision = 0;
export function getDataMode(): DataMode {
  if (typeof window === "undefined") return "demo";
  try {
    return localStorage.getItem(MODE_KEY) === "live" ? "live" : "demo";
  } catch {
    return fallback;
  }
}
export function setDataMode(mode: DataMode) {
  fallback = mode;
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* In-memory mode is available when storage is blocked. */
  }
  window.dispatchEvent(new Event(EVENT));
}
export function resetDemoData() {
  try {
    localStorage.removeItem(DEMO_STORAGE_KEY);
  } catch {
    /* Demo transport also listens for this reset event. */
  }
  revision++;
  window.dispatchEvent(new Event("air-power-demo-reset"));
  window.dispatchEvent(new Event(EVENT));
}
function subscribe(notify: () => void) {
  window.addEventListener(EVENT, notify);
  window.addEventListener("storage", notify);
  return () => {
    window.removeEventListener(EVENT, notify);
    window.removeEventListener("storage", notify);
  };
}
export function useDataMode() {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => `${getDataMode()}:${revision}`,
    () => "demo:0",
  );
  return {
    mode: snapshot.split(":")[0] as DataMode,
    key: snapshot,
    setMode: setDataMode,
    resetDemo: resetDemoData,
  };
}
