import { useCallback, useEffect, useState } from "react";
import { checkUpdate, getUpdateInfo } from "@/lib/api";
import type { UpdateInfo } from "@/types/models";

/**
 * Fetches the version/update snapshot from the backend on mount.
 * `check()` forces a fresh GitHub comparison (used by the manual button).
 */
export function useUpdate() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let alive = true;
    void getUpdateInfo()
      .then((i) => {
        if (alive) setInfo(i);
      })
      .catch(() => {
        /* update check is best-effort; ignore failures */
      });
    return () => {
      alive = false;
    };
  }, []);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      setInfo(await checkUpdate());
    } catch {
      /* ignore — keep last known info */
    } finally {
      setChecking(false);
    }
  }, []);

  return { info, checking, check };
}
