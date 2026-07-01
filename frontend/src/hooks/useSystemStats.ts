import { useEffect, useState } from "react";
import { getSystemStats } from "@/lib/api";
import type { SystemStats } from "@/types/models";

/**
 * Polls GET /api/system/stats every 2s while `enabled` is true. Polling
 * pauses (interval cleared) when disabled — e.g. the status bar is collapsed —
 * so no requests fire in the background. Errors are swallowed; the last good
 * snapshot stays on screen.
 */
export function useSystemStats(enabled: boolean) {
  const [stats, setStats] = useState<SystemStats | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const s = await getSystemStats();
        if (!cancelled) setStats(s);
      } catch {
        // endpoint unreachable; keep last snapshot
      }
    };
    void refresh();
    const t = setInterval(refresh, 2_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [enabled]);

  return stats;
}
