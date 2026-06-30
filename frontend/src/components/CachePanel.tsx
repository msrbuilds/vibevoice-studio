import { useEffect, useRef, useState } from "react";
import { Database, Download, FolderOpen, Pause, Play, Trash2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import {
  cacheAudioUrl,
  clearCache,
  deleteCacheEntry,
  listCache,
  openCacheFolder,
  type CacheEntryInfo,
  type CacheListResponse,
} from "@/lib/api";
import { GenerationDetailModal } from "./GenerationDetailModal";
import { useConfirm } from "./ConfirmProvider";

interface Props {
  isDark: boolean;
  onCountChange?: (count: number) => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(t: number): string {
  return new Date(t * 1000).toLocaleString();
}

// Defensive display name: prefer the server-derived `name`, but fall back to a
// hash-based label so the playlist still works against an older backend that
// doesn't yet return `name` (transition period before a restart).
function displayName(e: { name?: string | null; hash: string }): string {
  const n = (e.name ?? "").trim();
  return n || `Generation ${e.hash.slice(0, 8)}`;
}

function slugify(name: string, hash: string): string {
  const s = (name ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return s || `generation-${hash.slice(0, 8)}`;
}

/**
 * Fetches + polls the synthesis cache list. Exposes a manual `refresh()` so
 * embedded consumers (e.g. SettingsMenu) can refresh after a Clear action.
 */
export function useCacheData(onCountChange?: (count: number) => void) {
  const [data, setData] = useState<CacheListResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const d = await listCache();
      setData(d);
      onCountChange?.(d.entry_count);
    } catch {
      // Cache endpoint may not be reachable; ignore.
    }
  };

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onClear = async () => {
    setBusy(true);
    try {
      await clearCache();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (hash: string) => {
    setBusy(true);
    try {
      await deleteCacheEntry(hash);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return { data, busy, refresh, onClear, onDelete };
}

interface BodyProps {
  isDark: boolean;
  data: CacheListResponse | null;
  busy: boolean;
  onClear: () => void;
  onDelete: (hash: string) => void;
}

/** Reusable cache list body — rendered as a Recent generations playlist. */
export function CacheBody({ isDark, data, busy, onClear, onDelete }: BodyProps) {
  const confirm = useConfirm();
  const [playingHash, setPlayingHash] = useState<string | null>(null);
  const [detail, setDetail] = useState<CacheEntryInfo | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Create the shared audio element once on mount
  useEffect(() => {
    const audio = new Audio();
    audio.addEventListener("ended", () => setPlayingHash(null));
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  const handleRowPlay = (e: React.MouseEvent, entry: CacheEntryInfo) => {
    e.stopPropagation();
    const audio = audioRef.current;
    if (!audio) return;
    if (playingHash === entry.hash) {
      // Toggle pause
      audio.pause();
      setPlayingHash(null);
    } else {
      audio.src = cacheAudioUrl(entry.hash);
      audio.currentTime = 0;
      void audio.play().then(() => {
        setPlayingHash(entry.hash);
      }).catch(() => {
        setPlayingHash(null);
      });
    }
  };

  const stopSharedAudio = (hash?: string) => {
    const audio = audioRef.current;
    if (!audio) return;
    if (hash === undefined || playingHash === hash) {
      audio.pause();
      audio.src = "";
      setPlayingHash(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, hash: string) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Delete this generation?",
      message: "This removes the cached clip. It can be regenerated later.",
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    stopSharedAudio(hash);
    await onDelete(hash);
  };

  const handleClear = async () => {
    const ok = await confirm({
      title: "Clear all generations?",
      message: "This deletes every cached clip. Next synthesis will run the model again.",
      confirmLabel: "Clear all",
      danger: true,
    });
    if (!ok) return;
    stopSharedAudio();
    onClear();
  };

  const handleDownload = async (e: React.MouseEvent, entry: CacheEntryInfo) => {
    e.stopPropagation();
    try {
      const res = await fetch(cacheAudioUrl(entry.hash));
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `${slugify(displayName(entry), entry.hash)}.wav`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch {
      // Download failed silently; the row still exists
    }
  };

  if (!data) {
    return (
      <div className="px-4 py-6 text-center text-sm">
        <span className={isDark ? "text-zinc-400" : "text-gray-600"}>
          Loading…
        </span>
      </div>
    );
  }

  return (
    <>
      {/* Header — section heading on the left, icon actions on the right */}
      <div className="flex items-center justify-between mb-2">
        <h3
          className={`text-xs font-semibold uppercase tracking-wide ${
            isDark ? "text-zinc-400" : "text-gray-600"
          }`}
        >
          Recent generations
        </h3>
        <div className="flex items-center gap-0.5">
          {data.directory && (
            <button
              type="button"
              title={`Open cache folder: ${data.directory}`}
              onClick={() => void openCacheFolder()}
              className={`p-1 rounded transition-colors ${
                isDark
                  ? "text-zinc-400 hover:text-orange-400"
                  : "text-gray-600 hover:text-orange-600"
              } ${focusRing}`}
            >
              <FolderOpen className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={handleClear}
            disabled={busy || data.entry_count === 0}
            title="Clear all"
            className={`p-1 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              isDark
                ? "text-zinc-400 hover:text-red-400"
                : "text-gray-600 hover:text-red-700"
            } ${focusRing}`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Playlist */}
      <div className="max-h-80 overflow-y-auto">
        {data.entries.length === 0 ? (
          <div
            className={`px-4 py-6 text-center text-sm ${
              isDark ? "text-zinc-400" : "text-gray-600"
            }`}
          >
            No generations yet.
          </div>
        ) : (
          <ul>
            {data.entries.map((e) => {
              const isPlaying = playingHash === e.hash;
              return (
                <li
                  key={e.hash}
                  className={`px-3 py-2.5 border-b last:border-b-0 flex items-center gap-2 cursor-pointer transition-colors ${
                    isDark
                      ? "border-zinc-800 hover:bg-zinc-800/50"
                      : "border-gray-100 hover:bg-gray-50"
                  }`}
                  onClick={() => setDetail(e)}
                  title="Click to open detail"
                >
                  {/* Play / pause button */}
                  <button
                    type="button"
                    onClick={(ev) => handleRowPlay(ev, e)}
                    disabled={busy}
                    className={`shrink-0 w-7 h-7 flex items-center justify-center rounded-full transition-colors ${
                      isPlaying
                        ? "bg-orange-600/30 text-orange-400"
                        : isDark
                          ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
                          : "bg-gray-200 hover:bg-gray-300 text-gray-600"
                    } ${focusRing}`}
                    title={isPlaying ? "Pause" : "Play"}
                  >
                    {isPlaying ? (
                      <Pause className="w-3.5 h-3.5" />
                    ) : (
                      <Play className="w-3.5 h-3.5" />
                    )}
                  </button>

                  {/* Name + meta */}
                  <div className="flex-1 min-w-0">
                    <div
                      className={`text-sm font-medium truncate ${
                        isDark ? "text-zinc-200" : "text-gray-800"
                      }`}
                    >
                      {displayName(e)}
                    </div>
                    <div
                      className={`text-xs mt-0.5 truncate ${
                        isDark ? "text-zinc-400" : "text-gray-600"
                      }`}
                    >
                      {e.duration_sec.toFixed(1)}s · {formatBytes(e.size_bytes)} · {formatDate(e.created_at)}
                    </div>
                  </div>

                  {/* Download + Delete */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={(ev) => void handleDownload(ev, e)}
                      disabled={busy}
                      className={`p-1 rounded transition-colors ${
                        isDark
                          ? "text-zinc-400 hover:text-orange-400"
                          : "text-gray-600 hover:text-orange-600"
                      } ${focusRing}`}
                      title="Download WAV"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(ev) => void handleDelete(ev, e.hash)}
                      disabled={busy}
                      className={`p-1 rounded transition-colors ${
                        isDark
                          ? "text-zinc-400 hover:text-red-400"
                          : "text-gray-600 hover:text-red-700"
                      } ${focusRing}`}
                      title="Delete this entry"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Detail modal */}
      {detail && (
        <GenerationDetailModal
          isDark={isDark}
          entry={detail}
          onClose={() => setDetail(null)}
        />
      )}
    </>
  );
}

/** Standalone trigger-button popover (legacy; SettingsMenu uses CacheBody). */
export function CachePanel({ isDark, onCountChange }: Props) {
  const [open, setOpen] = useState(false);
  const { data, busy, onClear, onDelete } = useCacheData(onCountChange);

  const summary = data ? (
    <>
      <Database className="w-4 h-4" />
      Cache{" "}
      <span className={`text-xs ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
        {data.entry_count}/{data.max_entries}
      </span>
    </>
  ) : (
    <>
      <Database className="w-4 h-4" />
      Cache
    </>
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        } ${focusRing}`}
        title="Persistent synthesis cache"
      >
        {summary}
      </button>

      {open && data && (
        <div
          className={`absolute right-0 top-full mt-2 w-96 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <div className="absolute right-2 top-2 z-10">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className={`p-1 rounded ${
                isDark
                  ? "text-zinc-400 hover:text-zinc-300"
                  : "text-gray-600 hover:text-gray-600"
              } ${focusRing}`}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <CacheBody
            isDark={isDark}
            data={data}
            busy={busy}
            onClear={onClear}
            onDelete={onDelete}
          />
        </div>
      )}
    </div>
  );
}
