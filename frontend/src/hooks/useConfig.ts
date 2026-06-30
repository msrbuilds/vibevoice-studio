import { useCallback, useEffect, useState } from "react";
import { getConfig, ApiError } from "@/lib/api";
import type { ConfigResponse } from "@/types/models";

export interface UseConfigResult {
  config: ConfigResponse | null;
  loading: boolean;
  error: string | null;
  /** Refetch /api/config. Call after switching engines so the active
   *  engine's device/dtype/sample-rate are reflected (they're stale otherwise). */
  refresh: () => Promise<void>;
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const c = await getConfig();
      setConfig(c);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { config, loading, error, refresh };
}
