import { useEffect, useState } from "react";
import { getConfig, ApiError } from "@/lib/api";
import type { ConfigResponse } from "@/types/models";

export interface UseConfigResult {
  config: ConfigResponse | null;
  loading: boolean;
  error: string | null;
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((c) => {
        if (!cancelled) {
          setConfig(c);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { config, loading, error };
}
