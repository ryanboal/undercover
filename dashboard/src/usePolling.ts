import { useCallback, useEffect, useState } from "react";
import { getJson } from "./api";

export const POLL_MS = 2000;

interface Polled<T> {
  data?: T;
  error?: string;
}

export function usePolling<T>(
  path: string,
): Polled<T> & { refresh: () => void } {
  const [polled, setPolled] = useState<Polled<T>>({});
  const [loads, setLoads] = useState(0);

  useEffect(() => {
    let current = true;
    const load = () => {
      getJson<T>(path).then(
        (data) => {
          if (current) setPolled({ data });
        },
        (error: unknown) => {
          if (current) {
            const message =
              error instanceof Error ? error.message : String(error);
            setPolled((before) => ({ ...before, error: message }));
          }
        },
      );
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [path, loads]);

  const refresh = useCallback(() => {
    setLoads((count) => count + 1);
  }, []);
  return { ...polled, refresh };
}
