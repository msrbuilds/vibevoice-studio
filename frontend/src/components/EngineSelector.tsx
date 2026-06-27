import { useState } from "react";
import { Cpu, Loader2, Volume2 } from "lucide-react";
import type { EngineInfo } from "@/types/models";

interface Props {
  isDark: boolean;
  engines: EngineInfo[];
  activeName: string | null;
  onSelect: (name: string) => Promise<void>;
  onLoad: (name: string) => Promise<void>;
  onInstall: (name: string) => void;
  onDownload: (name: string) => void;
}

export function EngineSelector({
  isDark,
  engines,
  activeName,
  onSelect,
  onLoad,
  onInstall,
  onDownload,
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
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title="Switch TTS engine"
      >
        <Cpu className="w-4 h-4" />
        {summary}
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-96 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <div
            className={`px-4 py-3 border-b ${
              isDark ? "border-zinc-800" : "border-gray-200"
            }`}
          >
            <div
              className={`text-sm font-semibold ${
                isDark ? "text-white" : "text-gray-900"
              }`}
            >
              TTS engine
            </div>
            <div
              className={`text-xs mt-0.5 ${
                isDark ? "text-zinc-500" : "text-gray-500"
              }`}
            >
              Switch between backends. Only one runs at a time.
            </div>
          </div>

          <ul className="max-h-80 overflow-y-auto">
            {engines.map((e) => {
              const isActive = e.name === activeName;
              const switching = switchingTo === e.name;
              return (
                <li
                  key={e.name}
                  className={`px-4 py-3 border-b last:border-b-0 ${
                    isDark ? "border-zinc-800" : "border-gray-100"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                        isActive
                          ? "bg-teal-600/20 text-teal-400"
                          : isDark
                            ? "bg-zinc-800 text-zinc-400"
                            : "bg-gray-100 text-gray-500"
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
                          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-teal-600/20 text-teal-300">
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
                        className={`text-[10px] mt-1 ${
                          isDark ? "text-zinc-500" : "text-gray-500"
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
                              ? "bg-teal-700/40 hover:bg-teal-700/60 text-teal-200"
                              : "bg-teal-50 hover:bg-teal-100 text-teal-700"
                          }`}
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
                              ? "bg-teal-700/40 hover:bg-teal-700/60 text-teal-200"
                              : "bg-teal-50 hover:bg-teal-100 text-teal-700"
                          }`}
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
                              ? "bg-teal-600/20 text-teal-300 cursor-default"
                              : isDark
                                ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                                : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                          }`}
                        >
                          {isActive
                            ? "Currently active"
                            : switching
                              ? "Loading…"
                              : `Switch to ${e.display_name}`}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <div
            className={`px-4 py-2 text-[11px] border-t ${
              isDark
                ? "border-zinc-800 text-zinc-500"
                : "border-gray-200 text-gray-500"
            }`}
          >
            Switching unloads the current model. First synthesis may take
            a few seconds while weights load.
          </div>
        </div>
      )}
    </div>
  );
}
