import { useEffect, useRef, useState } from "react";
import { Download, Loader2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getModelDownloadStatus, startModelDownload } from "@/lib/api";
import type { DownloadStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  engineName: string;
  displayName: string;
  onClose: () => void;
  onDone: () => void;
}

// Mirrors the catalog sizes in backend/scripts/download_models.py.
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
  omnivoice: "~3.3 GB",
  voxcpm: "~5 GB",
};

const fmtBytes = (b: number): string =>
  b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(0)} MB`;

const fmtSpeed = (bps: number | null): string =>
  bps && bps > 0 ? `${(bps / 1e6).toFixed(1)} MB/s` : "—";

const fmtEta = (s: number | null): string => {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
};

export function DownloadModelDialog({
  isDark,
  engineName,
  displayName,
  onClose,
  onDone,
}: Props) {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<DownloadStatus>({
    engine: engineName,
    state: "idle",
    percent: null,
    downloaded_bytes: 0,
    total_bytes: null,
    speed_bps: null,
    eta_sec: null,
    current_file: null,
    log: [],
    error: null,
    returncode: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);
  const sizeLabel = MODEL_SIZES[engineName] ?? "";

  const poll = async () => {
    try {
      const s = await getModelDownloadStatus(engineName);
      if (s.state === "idle") {
        // We started a download but the server reports no job — it likely
        // restarted and lost the in-memory state. Surface a retryable error
        // instead of polling forever.
        setStatus((prev) => ({
          ...prev,
          state: "error",
          error:
            "Download was interrupted (the server may have restarted). Retry to resume.",
          log: [
            ...prev.log,
            "Download interrupted — server state was lost. Retry to resume.",
          ],
        }));
        return;
      }
      setStatus(s);
      if (s.state === "downloading") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      } else if (s.state === "done") {
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
    setStatus((prev) => ({ ...prev, state: "downloading", error: null, log: [] }));
    try {
      await startModelDownload(engineName);
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        error: err instanceof Error ? err.message : String(err),
        log: [err instanceof Error ? err.message : String(err)],
      }));
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

  const downloading = status.state === "downloading";
  const failed = status.state === "error";
  const pct = status.percent ?? 0;

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
            {downloading ? (
              <Loader2 className="w-4 h-4 animate-spin text-orange-400" />
            ) : (
              <Download className="w-4 h-4 text-orange-400" />
            )}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {downloading
                ? `Downloading ${displayName}…`
                : failed
                  ? `${displayName} download failed`
                  : `Download ${displayName}`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={downloading}
            className={`p-1 rounded ${
              downloading
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
            <p className={`text-sm ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
              {displayName} needs a {sizeLabel} model download before it can run.
              This happens once; the weights are cached locally afterward.
            </p>
          ) : (
            <>
              <div className="space-y-1">
                <div
                  className={`h-2.5 w-full rounded-full overflow-hidden ${
                    isDark ? "bg-zinc-800" : "bg-gray-200"
                  }`}
                >
                  <div
                    className={`h-full bg-orange-500 transition-[width] duration-500 ${
                      status.total_bytes ? "" : "animate-pulse"
                    }`}
                    style={{ width: `${status.total_bytes ? pct : 100}%` }}
                  />
                </div>
                <div
                  className={`flex justify-between text-[11px] ${
                    isDark ? "text-zinc-400" : "text-gray-600"
                  }`}
                >
                  <span>
                    {status.total_bytes
                      ? `${pct.toFixed(0)}% · ${fmtBytes(status.downloaded_bytes)} / ${fmtBytes(status.total_bytes)}`
                      : `${fmtBytes(status.downloaded_bytes)} downloaded`}
                  </span>
                  <span>
                    {fmtSpeed(status.speed_bps)}
                    {downloading && status.eta_sec != null
                      ? ` · ETA ${fmtEta(status.eta_sec)}`
                      : ""}
                  </span>
                </div>
              </div>
              <pre
                ref={logRef}
                className={`h-48 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                  isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                }`}
              >
                {status.log.length ? status.log.join("\n") : "Starting…"}
              </pre>
            </>
          )}

          <div className="flex justify-end gap-2">
            {!started && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
              >
                {`Download (${sizeLabel})`}
              </button>
            )}
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={downloading}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                downloading
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
