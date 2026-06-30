import { useEffect, useState } from "react";
import { AudioWaveform, Binary, Cpu, Mic2, Moon, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Sun, Trash2, Volume2 } from "lucide-react";
import type { ConfigResponse, Voice, VoiceMetadata } from "@/types/models";
import { UploadVoiceDialog } from "./UploadVoiceDialog";
import { VoiceMetaDialog } from "./VoiceMetaDialog";
import { ThemeToggle } from "./ThemeToggle";
import { focusRing } from "@/lib/theme";
import { defaultVoiceLibraryOpen } from "@/lib/layout";
import { useConfirm } from "./ConfirmProvider";

interface Props {
  voices: Voice[];
  config: ConfigResponse | null;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  onUploadVoice: (file: File, meta: VoiceMetadata) => Promise<unknown>;
  onRemoveVoice: (id: string) => Promise<void>;
  onUpdateVoiceMeta: (voiceId: string, meta: VoiceMetadata) => Promise<unknown>;
  supportsVoiceCloning: boolean;
  selectedVoiceId?: string | null;
  onSelectVoice?: (voiceId: string) => void;
}

export function VoiceLibrary({
  voices,
  config,
  theme,
  onThemeToggle,
  onUploadVoice,
  onRemoveVoice,
  onUpdateVoiceMeta,
  supportsVoiceCloning,
  selectedVoiceId,
  onSelectVoice,
}: Props) {
  const confirm = useConfirm();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editingVoice, setEditingVoice] = useState<Voice | null>(null);

  const LS_KEY = "vs.voiceLibrary.open";
  const [open, setOpen] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "true";
    return typeof window !== "undefined"
      ? defaultVoiceLibraryOpen(window.innerWidth)
      : true;
  });
  useEffect(() => {
    localStorage.setItem(LS_KEY, open ? "true" : "false");
  }, [open]);

  const builtins = voices.filter((v) => v.source === "builtin");
  const uploads = voices.filter((v) => v.source === "upload");

  const isDark = theme === "dark";
  // Surface tokens — the sidebar has its own palette in both themes so it
  // reads as a distinct panel from the main content.
  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-400" : "text-gray-600";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const subtle = isDark ? "text-zinc-400" : "text-gray-600";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-orange-400"
    : "text-gray-600 hover:text-orange-600";
  const empty = isDark ? "text-zinc-600" : "text-gray-600";

  // Voice-row background states — shared by both lists so built-in and uploaded
  // voices look identical. One coherent scale (rest → hover → selected), all
  // orange-accented and consistent across light/dark. Selected adds a ring so it
  // reads clearly even where the hover tint is close. (Avoids the old tangle of
  // an inline `hover:bg-orange-*` fighting the `${hover}` token, and the loud
  // solid-orange dark fill vs. subtle light tint mismatch.)
  const rowState = (selected: boolean) =>
    selected
      ? "bg-orange-100 text-orange-900 ring-1 ring-orange-300 dark:bg-orange-500/15 dark:text-orange-50 dark:ring-orange-500/50"
      : "bg-white text-gray-700 hover:bg-orange-50 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-orange-500/10";
  // Leading mic/speaker icon: orange in dark, neutral-until-selected in light.
  const rowIcon = (selected: boolean) =>
    selected ? "text-orange-600 dark:text-orange-300" : "text-gray-400 dark:text-orange-400/80";
  // Secondary gender label: subtle at rest, tinted to match when selected.
  const rowMeta = (selected: boolean) =>
    selected ? "text-orange-700/90 dark:text-orange-200/80" : subtle;

  if (!open) {
    return (
      <aside
        className={`w-12 shrink-0 z-10 border-r flex flex-col items-center pt-4 gap-3 transition-colors ${surface} ${border}`}
      >
        <img
          src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
          alt="Voice Studio logo"
          width={36}
          height={36}
          className="w-9 h-9 rounded-lg"
        />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
          title="Open voice library"
        >
          <PanelLeftOpen className="w-5 h-5" />
        </button>
        <button
          type="button"
          onClick={onThemeToggle}
          className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
          title="Toggle theme"
        >
          {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`w-64 shrink-0 z-10 border-r flex flex-col transition-colors ${surface} ${border}`}
    >
      <div className={`p-3 xxl:p-4 border-b flex items-center gap-3 ${border}`}>
        <img
          src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
          alt="Voice Studio logo"
          width={36}
          height={36}
          className="w-9 h-9 rounded-lg shrink-0"
        />
        <div className="min-w-0 flex-1">
          <h1 className={`font-semibold text-sm truncate ${isDark ? "text-white" : "text-gray-900"}`}>
            Voice Studio by MSR
          </h1>
          <p className={`text-xs truncate ${heading}`}>Local · {config?.model_id ?? "—"}</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className={`p-1 rounded transition-colors ${iconBtn} ${focusRing}`}
          title="Collapse voice library"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-4">
        {/* Built-in voices */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Built-in voices
          </h2>
          <ul className="space-y-1">
            {builtins.map((v) => {
              const isSelected = onSelectVoice !== undefined && selectedVoiceId === v.id;
              return (
              <li
                key={v.id}
                onClick={onSelectVoice ? () => onSelectVoice(v.id) : undefined}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${rowState(isSelected)} ${
                  onSelectVoice ? "cursor-pointer" : ""
                }`}
              >
                <Volume2 className={`w-4 h-4 shrink-0 ${rowIcon(isSelected)}`} />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${rowMeta(isSelected)}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 ${iconBtn} ${focusRing}`}
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              </li>
              );
            })}
            {builtins.length === 0 && (
              <li className={`text-xs italic px-2 py-1.5 ${empty}`}>
                No built-in voices. Drop .wav files into backend/voices/.
              </li>
            )}
          </ul>
        </section>

        {/* User uploads — hidden when the active engine doesn't support
            voice cloning (Kokoro uses its own built-in voice catalog). */}
        {supportsVoiceCloning && (
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
              My voices
            </h2>
            <button
              type="button"
              onClick={() => setUploadOpen(true)}
              className={`p-1 transition-colors ${iconBtn} ${focusRing}`}
              title="Upload voice"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <ul className="space-y-1">
            {uploads.map((v) => {
              const isSelected = onSelectVoice !== undefined && selectedVoiceId === v.id;
              return (
              <li
                key={v.id}
                onClick={onSelectVoice ? () => onSelectVoice(v.id) : undefined}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${rowState(isSelected)} ${
                  onSelectVoice ? "cursor-pointer" : ""
                }`}
              >
                <Mic2 className={`w-4 h-4 shrink-0 ${isSelected ? "text-orange-600 dark:text-orange-300" : "text-orange-500 dark:text-orange-400"}`} />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${rowMeta(isSelected)}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 ${iconBtn} ${focusRing}`}
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={async (e) => {
                    e.stopPropagation();
                    const ok = await confirm({
                      title: `Delete "${v.name}"?`,
                      message: "This permanently removes the uploaded voice.",
                      confirmLabel: "Delete",
                      danger: true,
                    });
                    if (ok) void onRemoveVoice(v.id);
                  }}
                  className={`p-1 dark:text-red-400 ${iconBtn} ${focusRing}`}
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
              );
            })}
            {uploads.length === 0 && (
              <li className={`text-xs italic px-2 py-1.5 ${empty}`}>
                Click + to upload a voice.
              </li>
            )}
          </ul>
        </section>
        )}
      </div>

      {/* Footer — appearance + backend info, pinned to the bottom of the sidebar */}
      <div className={`p-4 border-t space-y-4 shrink-0 ${border}`}>
        <section>
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Appearance
          </h2>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
        </section>
        {config && (
          <section>
            <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
              Backend
            </h2>
            <div className={`text-xs ${subtle} flex items-center gap-4`}>
              <span className="flex items-center gap-1.5" title="Compute device">
                <Cpu className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.device}</span>
              </span>
              <span className="flex items-center gap-1.5" title="Compute precision (dtype)">
                <Binary className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.dtype}</span>
              </span>
              <span className="flex items-center gap-1.5" title="Output sample rate">
                <AudioWaveform className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>
                  {config.sampling_rate > 0
                    ? `${(config.sampling_rate / 1000).toFixed(config.sampling_rate % 1000 === 0 ? 0 : 1)} kHz`
                    : "—"}
                </span>
              </span>
            </div>
          </section>
        )}
      </div>

      <UploadVoiceDialog
        open={uploadOpen}
        theme={theme}
        onClose={() => setUploadOpen(false)}
        onUpload={onUploadVoice}
      />

      <VoiceMetaDialog
        voice={editingVoice}
        theme={theme}
        onClose={() => setEditingVoice(null)}
        onSave={async (meta) => {
          if (editingVoice) {
            await onUpdateVoiceMeta(editingVoice.id, meta);
            setEditingVoice(null);
          }
        }}
      />
    </aside>
  );
}
