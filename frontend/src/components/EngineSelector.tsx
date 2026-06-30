import { useState } from "react";
import { ChevronDown, Cpu, Loader2, Volume2, X } from "lucide-react";
import type { EngineInfo } from "@/types/models";
import { focusRing } from "@/lib/theme";

interface Props {
  isDark: boolean;
  engines: EngineInfo[];
  activeName: string | null;
  onSelect: (name: string) => Promise<void>;
  onLoad: (name: string) => Promise<void>;
  onInstall: (name: string) => void;
  onDownload: (name: string) => void;
  onDeleteWeights: (name: string) => void;
  onUninstall: (name: string) => void;
}

export function EngineSelector({
  isDark,
  engines,
  activeName,
  onSelect,
  onLoad,
  onInstall,
  onDownload,
  onDeleteWeights,
  onUninstall,
}: Props) {
  const [open, setOpen] = useState(false);
  const [switchingTo, setSwitchingTo] = useState<string | null>(null);
  const active = engines.find((e) => e.name === activeName);
  // Show "Engine" while the initial /api/engines fetch is in flight, or
  // the active engine name once we know it. If `engines` is empty after
  // the fetch (network/server error), keep showing "Engine" so the user
  // knows something's wrong but the button is still clickable to retry.
  const summary = active
    ? active.display_name
    : engines.length === 0
      ? "Engine…"
      : "Engine";

  const handleSelect = async (name: string) => {
    if (name === activeName) {
      setOpen(false);
      return;
    }
    setSwitchingTo(name);
    try {
      await onSelect(name);
      // Kick off an eager load so the spinner shows during model load.
      // onLoad resolves when the engine is ready.
      try {
        await onLoad(name);
      } catch {
        // Lazy-loaded engines may report load failures here; the
        // synthesize endpoint will retry on first call.
      }
    } finally {
      setSwitchingTo(null);
      setOpen(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`w-full flex items-center justify-between gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-white hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        } ${focusRing}`}
        title="Switch TTS engine"
      >
        <span className="flex items-center gap-2 min-w-0">
          <Cpu className="w-4 h-4 shrink-0" />
          <span className="truncate">{summary}</span>
        </span>
        <ChevronDown className="w-4 h-4 shrink-0 opacity-70" />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
          />

          {/* Modal */}
          <div
            className={`relative w-full max-w-3xl max-h-[85vh] flex flex-col rounded-xl shadow-2xl border ${
              isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
            }`}
          >
            <div
              className={`px-5 py-4 border-b flex items-start justify-between gap-3 shrink-0 ${
                isDark ? "border-zinc-800" : "border-gray-200"
              }`}
            >
              <div>
                <div
                  className={`text-sm font-semibold ${
                    isDark ? "text-white" : "text-gray-900"
                  }`}
                >
                  TTS engine
                </div>
                <div
                  className={`text-xs mt-0.5 ${
                    isDark ? "text-zinc-400" : "text-gray-600"
                  }`}
                >
                  Switch between backends. Only one runs at a time.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className={`p-1 rounded transition-colors ${
                  isDark
                    ? "text-zinc-400 hover:text-zinc-300"
                    : "text-gray-600 hover:text-gray-600"
                } ${focusRing}`}
                title="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <ul className="flex-1 overflow-y-auto grid grid-cols-1 sm:grid-cols-2 gap-3 p-4">
            {engines.map((e) => {
              const isActive = e.name === activeName;
              const switching = switchingTo === e.name;
              return (
                <li
                  key={e.name}
                  className={`rounded-lg border p-4 ${
                    isDark ? "border-zinc-800 bg-zinc-950/40" : "border-gray-300 bg-gray-50"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                        isActive
                          ? isDark ? "bg-orange-600/20 text-orange-400" : "bg-orange-100 text-orange-700"
                          : isDark
                            ? "bg-zinc-800 text-zinc-400"
                            : "bg-gray-200 text-gray-700"
                      }`}
                    >
                      {switching ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Volume2 className="w-4 h-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm font-medium ${
                            isDark ? "text-white" : "text-gray-900"
                          }`}
                        >
                          {e.display_name}
                        </span>
                        {isActive && (
                          <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${isDark ? "bg-orange-600/20 text-orange-300" : "bg-orange-100 text-orange-700"}`}>
                            Active
                          </span>
                        )}
                        {e.loaded && !isActive && (
                          <span
                            className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                              isDark
                                ? "bg-zinc-800 text-zinc-400"
                                : "bg-gray-200 text-gray-600"
                            }`}
                          >
                            Loaded
                          </span>
                        )}
                      </div>
                      <p
                        className={`text-xs mt-0.5 ${
                          isDark ? "text-zinc-400" : "text-gray-600"
                        }`}
                      >
                        {e.description}
                      </p>
                      <div
                        className={`text-xs mt-1.5 ${
                          isDark ? "text-zinc-400" : "text-gray-600"
                        }`}
                      >
                        {e.supports_voice_cloning
                          ? "voice cloning"
                          : "built-in voices only"}
                        {" · "}
                        {e.max_speakers === 1
                          ? "single speaker"
                          : `up to ${e.max_speakers} speakers`}
                        {" · "}
                        {e.sample_rate
                          ? `${(e.sample_rate / 1000).toFixed(0)} kHz`
                          : "—"}
                      </div>
                      {e.installed === false ? (
                        <button
                          type="button"
                          onClick={() => {
                            onInstall(e.name);
                            setOpen(false);
                          }}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isDark
                              ? "bg-orange-700/40 hover:bg-orange-700/60 text-orange-200"
                              : "bg-orange-50 hover:bg-orange-100 text-orange-700"
                          } ${focusRing}`}
                        >
                          {`Install ${e.display_name}`}
                        </button>
                      ) : e.downloaded === false ? (
                        <button
                          type="button"
                          onClick={() => {
                            onDownload(e.name);
                            setOpen(false);
                          }}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isDark
                              ? "bg-orange-700/40 hover:bg-orange-700/60 text-orange-200"
                              : "bg-orange-50 hover:bg-orange-100 text-orange-700"
                          } ${focusRing}`}
                        >
                          {`Download ${e.display_name}`}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleSelect(e.name)}
                          disabled={isActive}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isActive
                              ? isDark ? "bg-orange-600/20 text-orange-300 cursor-default" : "bg-orange-100 text-orange-800 cursor-default"
                              : isDark
                                ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                                : "bg-gray-200 hover:bg-gray-300 text-gray-900"
                          } ${focusRing}`}
                        >
                          {isActive
                            ? "Currently active"
                            : switching
                              ? "Loading…"
                              : `Switch to ${e.display_name}`}
                        </button>
                      )}
                      {/* Secondary destructive actions — hidden for the active
                          engine (switching away first is required). */}
                      {!isActive && (e.downloaded || (e.installed && (e.name === "chatterbox" || e.name === "omnivoice" || e.name === "voxcpm" || e.name === "qwen"))) && (
                        <div className="mt-1.5 flex items-center gap-3">
                          {e.downloaded && (
                            <button
                              type="button"
                              onClick={() => {
                                onDeleteWeights(e.name);
                                setOpen(false);
                              }}
                              className={`text-[11px] font-medium transition-colors ${
                                isDark
                                  ? "text-zinc-400 hover:text-red-400"
                                  : "text-gray-600 hover:text-red-700"
                              } ${focusRing}`}
                            >
                              Delete weights
                            </button>
                          )}
                          {e.installed && (e.name === "chatterbox" || e.name === "omnivoice" || e.name === "voxcpm" || e.name === "qwen") && (
                            <button
                              type="button"
                              onClick={() => {
                                onUninstall(e.name);
                                setOpen(false);
                              }}
                              className={`text-[11px] font-medium transition-colors ${
                                isDark
                                  ? "text-zinc-400 hover:text-red-400"
                                  : "text-gray-600 hover:text-red-700"
                              } ${focusRing}`}
                            >
                              Uninstall environment
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
            </ul>

            <div
              className={`px-5 py-3 text-[11px] border-t shrink-0 ${
                isDark
                  ? "border-zinc-800 text-zinc-400"
                  : "border-gray-200 text-gray-600"
              }`}
            >
              Switching unloads the current model. First synthesis may take
              a few seconds while weights load.
            </div>
          </div>
        </div>
      )}
    </>
  );
}
