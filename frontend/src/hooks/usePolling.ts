"use client";
import { useState, useEffect, useRef, useCallback } from "react";

export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs = 3000,
  enabled = true,
) {
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<Error | null>(null);
  const fnRef = useRef(fn);
  const cancelRef = useRef<() => void>(() => {});
  useEffect(() => {
    fnRef.current = fn;
  });
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const cancel = () => {
      cancelled = true;
      clearTimeout(timer);
    };
    cancelRef.current = cancel;
    setLoading(true);
    const poll = async () => {
      try {
        const result = await fnRef.current();
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err : new Error("Polling failed"));
      } finally {
        if (!cancelled) {
          setLoading(false);
          timer = setTimeout(poll, Math.max(100, intervalMs));
        }
      }
    };
    void poll();
    return cancel;
  }, [intervalMs, enabled, attempt]);
  const stop = useCallback(() => {
    cancelRef.current();
    setLoading(false);
  }, []);
  const refetch = useCallback(() => {
    setError(null);
    setAttempt((value) => value + 1);
  }, []);
  return { data, loading, error, stop, refetch };
}
