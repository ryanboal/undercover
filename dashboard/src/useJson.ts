import { useCallback, useEffect, useState } from "react";
import { getJson } from "./api";

export const POLL_MS = 2000;

interface Loaded<T> {
  data?: T;
  error?: string;
}

// Loads JSON from the API, and with poll set, loads it again every POLL_MS.
export function useJson<T>(
  path: string,
  poll: boolean,
): Loaded<T> & { refresh: () => void } {
  const [loaded, setLoaded] = useState<Loaded<T>>({});
  const [loads, setLoads] = useState(0);

  useEffect(() => {
    let current = true;
    const load = () => {
      getJson<T>(path).then(
        (data) => {
          if (current) setLoaded({ data });
        },
        (error: unknown) => {
          if (current) {
            const message =
              error instanceof Error ? error.message : String(error);
            setLoaded((before) => ({ ...before, error: message }));
          }
        },
      );
    };
    load();
    const timer = poll ? setInterval(load, POLL_MS) : undefined;
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [path, poll, loads]);

  const refresh = useCallback(() => {
    setLoads((count) => count + 1);
  }, []);
  return { ...loaded, refresh };
}
