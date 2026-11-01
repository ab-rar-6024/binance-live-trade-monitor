import { useEffect, useState } from "react";

/**
 * Calls `load` now and then every `intervalMs`. The data is cleared when `key` changes (for example a different coin),
 * and a result that arrives after the key has changed is ignored.
 */
export function usePolling<T>(load: () => Promise<T>, key: string, intervalMs: number): { data: T | null; failed: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const result = await load();
        if (!cancelled) {
          setData(result);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    setData(null);
    setFailed(false);
    run();
    const timer = window.setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // `load` is recreated on every render; `key` identifies what is being loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs]);

  return { data, failed };
}
