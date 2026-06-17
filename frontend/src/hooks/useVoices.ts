import { useCallback, useEffect, useState } from "react";
import { listVoices, uploadVoice, deleteVoice, ApiError } from "@/lib/api";
import type { Voice } from "@/types/models";

export interface UseVoicesResult {
  voices: Voice[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  upload: (file: File) => Promise<Voice>;
  remove: (id: string) => Promise<void>;
}

export function useVoices(): UseVoicesResult {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listVoices();
      setVoices(data);
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

  const upload = useCallback(
    async (file: File) => {
      const result = await uploadVoice(file);
      await refresh();
      return result as unknown as Voice;
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await deleteVoice(id);
      await refresh();
    },
    [refresh],
  );

  return { voices, loading, error, refresh, upload, remove };
}
