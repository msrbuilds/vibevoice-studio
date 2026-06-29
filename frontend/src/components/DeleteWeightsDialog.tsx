import { useEffect, useRef, useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getDeleteWeightsStatus, startDeleteWeights } from "@/lib/api";
import type { DeleteWeightsStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onDone: () => void;
}

// Mirrors the catalog sizes in backend/scripts/download_models.py (all 4 engines).
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
  chatterbox: "~500 MB",
  omnivoice: "~3.3 GB",
};

export function DeleteWeightsDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onDone,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<DeleteWeightsStatus>({
    engine: engineName,
    state: "idle",
    log: [],
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);
  const sizeLabel = MODEL_SIZES[engineName] ?? "";

  const poll = async () => {
    try {
      const s = await getDeleteWeightsStatus(engineName);
      // The deleter is a global singleton; ignore a snapshot that belongs to a
      // different engine (shouldn't happen via the single-modal UI, but guard).
      if (s.engine && s.engine !== engineName) {
        timerRef.current = window.setTimeout(() => void poll(), 800);
        return;
      }
      setStatus(s);
      if (s.state === "deleting") {
        timerRef.current = window.setTimeout(() => void poll(), 800);
      } else if (s.state === "deleted") {
        onDone();
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
    setStatus({ engine: engineName, state: "deleting", log: [], error: null });
    try {
      await startDeleteWeights(engineName);
    } catch (err) {
      setStatus({
        engine: engineName,
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

  const deleting = status.state === "deleting";
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
            {deleting ? (
              <Loader2 className="w-4 h-4 animate-spin text-red-400" />
            ) : (
              <Trash2 className="w-4 h-4 text-red-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {deleting
                ? `Deleting ${displayName} weights…`
                : failed
                  ? `${displayName} delete failed`
                  : `Delete ${displayName} weights`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={deleting}
            className={`p-1 rounded ${
              deleting
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-600"
            } ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {!started ? (
            <p className={`text-sm ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
              This permanently deletes {displayName}'s cached model weights
              ({sizeLabel}) from disk. You can re-download them later from the
              engine menu. Continue?
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
                {`Delete weights (${sizeLabel})`}
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
              disabled={deleting}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                deleting
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
