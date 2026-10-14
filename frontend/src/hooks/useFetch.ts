"use client";
import { useState, useEffect, useCallback, useRef } from "react";

export function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const fnRef = useRef(fn);
  const generation = useRef(0);
  useEffect(() => {
    fnRef.current = fn;
  });
  const refetch = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    setError(null);
    try {
      const result = await fnRef.current();
      if (request === generation.current) setData(result);
    } catch (err) {
      if (request === generation.current)
        setError(err instanceof Error ? err : new Error("Request failed"));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    setData(null);
    void refetch();
    return () => {
      generation.current++;
    };
    // Callers explicitly declare the values that trigger a new request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refetch, ...deps]);
  return { data, error, loading, refetch };
}
