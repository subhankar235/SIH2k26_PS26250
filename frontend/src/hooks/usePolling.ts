'use client';
import { useState, useEffect, useRef } from 'react';

export function usePolling<T>(fn: () => Promise<T>, intervalMs = 3000, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(enabled);

  useEffect(() => {
    activeRef.current = enabled;
    if (!enabled) return;

    let timer: NodeJS.Timeout;
    const poll = async () => {
      try {
        const res = await fn();
        setData(res);
        setError(null);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
        if (activeRef.current) {
          timer = setTimeout(poll, intervalMs);
        }
      }
    };

    poll();
    return () => clearTimeout(timer);
  }, [fn, intervalMs, enabled]);

  return { data, loading, error, stop: () => { activeRef.current = false; } };
}
