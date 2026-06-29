import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getEngineInstallStatus, startEngineInstall } from "@/lib/api";
import type { InstallStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onInstalled: () => void;
}

export function InstallEngineDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onInstalled,
}: Props) {
  const [status, setStatus] = useState<InstallStatus>({
    state: "installing",
    log: [],
    returncode: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getEngineInstallStatus(engineName);
      setStatus(s);
      if (s.state === "installing") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      } else if (s.state === "installed") {
        onInstalled();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStatus({ state: "installing", log: [], returncode: null });
    try {
      await startEngineInstall(engineName);
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        returncode: -1,
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    void begin();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const installing = status.state === "installing";
  const done = status.state === "installed";
  const failed = status.state === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`w-full max-w-2xl rounded-xl border shadow-xl ${
          isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
        }`}
      >
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {installing && <Loader2 className="w-4 h-4 animate-spin text-orange-400" />}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {installing
                ? `Installing ${displayName}…`
                : done
                  ? `${displayName} installed`
                  : `${displayName} install failed`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={installing}
            className={`p-1 rounded ${
              installing
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-600"
            } ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <p className={`text-sm ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
            {installing
              ? `Building the isolated ${displayName} environment (venv + PyTorch + model package). This takes a few minutes.`
              : done
                ? `Done. Close this dialog, then switch to ${displayName} in the engine menu.`
                : "The install failed. Review the log below and retry."}
          </p>
          <pre
            ref={logRef}
            className={`h-72 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
              isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
            }`}
          >
            {status.log.length ? status.log.join("\n") : "Starting…"}
          </pre>
          <div className="flex justify-end gap-2">
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-700 hover:bg-orange-600 text-white ${focusRing}`}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={installing}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                installing
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              } ${focusRing}`}
            >
              {done ? "Done" : "Close"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
