import { useEffect, useRef, useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getUninstallStatus, startUninstallEngine } from "@/lib/api";
import type { UninstallStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onUninstalled: () => void;
}

export function UninstallEngineDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onUninstalled,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<UninstallStatus>({
    state: "idle",
    log: [],
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getUninstallStatus(engineName);
      setStatus(s);
      if (s.state === "uninstalling") {
        timerRef.current = window.setTimeout(() => void poll(), 800);
      } else if (s.state === "uninstalled") {
        onUninstalled();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        error: err instanceof Error ? err.message : String(err),
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStarted(true);
    setStatus({ state: "uninstalling", log: [], error: null });
    try {
      await startUninstallEngine(engineName);
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        error: err instanceof Error ? err.message : String(err),
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const uninstalling = status.state === "uninstalling";
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
            {uninstalling ? (
              <Loader2 className="w-4 h-4 animate-spin text-red-400" />
            ) : (
              <Trash2 className="w-4 h-4 text-red-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {uninstalling
                ? `Uninstalling ${displayName}…`
                : failed
                  ? `${displayName} uninstall failed`
                  : `Uninstall ${displayName} environment`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={uninstalling}
            className={`p-1 rounded ${
              uninstalling
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
          {!started ? (
            <p className={`text-sm ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
              This removes {displayName}'s isolated environment (its dedicated
              Python venv and packages) to free disk space. The model weights are
              not touched. You can reinstall it later from the engine menu. Continue?
            </p>
          ) : (
            <pre
              ref={logRef}
              className={`h-48 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
              }`}
            >
              {status.log.length ? status.log.join("\n") : "Starting…"}
            </pre>
          )}

          <div className="flex justify-end gap-2">
            {!started && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                Uninstall
              </button>
            )}
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white ${focusRing}`}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={uninstalling}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                uninstalling
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              } ${focusRing}`}
            >
              {started ? "Close" : "Cancel"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
