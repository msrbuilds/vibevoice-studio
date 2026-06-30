import { useEffect, useState } from "react";
import { Mic2, Moon, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Sun, Trash2, Volume2, Waves } from "lucide-react";
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
  const hover = isDark ? "hover:bg-zinc-900" : "hover:bg-gray-100";
  const empty = isDark ? "text-zinc-600" : "text-gray-600";

  if (!open) {
    return (
      <aside
        className={`w-12 shrink-0 z-10 border-r flex flex-col items-center pt-4 gap-3 transition-colors ${surface} ${border}`}
      >
        <div className="w-9 h-9 rounded-lg bg-orange-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-orange-400" />
        </div>
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
        <div className="w-9 h-9 rounded-lg bg-orange-600/20 flex items-center justify-center shrink-0">
          <Waves className="w-5 h-5 text-orange-400" />
        </div>
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
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm bg-white dark:bg-zinc-800 hover:bg-orange-200/30 dark:hover:bg-zinc-600 ${bodyText} ${hover} ${
                  onSelectVoice ? "cursor-pointer" : ""
                } ${isSelected ? "ring-1 ring-orange-300 bg-orange-200/30 text-black dark:bg-orange-900 dark:ring-orange-800 dark:text-white" : ""}`}
              >
                <Volume2 className={`w-4 h-4 dark:text-orange-400 ${subtle}`} />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 dark:text-orange-400 ${iconBtn} ${focusRing}`}
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
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm bg-white dark:bg-zinc-800 hover:bg-orange-200/30 dark:hover:bg-zinc-600 ${bodyText} ${hover} ${
                  onSelectVoice ? "cursor-pointer" : ""
                } ${isSelected ? "ring-1 ring-orange-500 bg-orange-300/10 dark:bg-orange-900 dark:ring-orange-800" : ""}`}
              >
                <Mic2 className="w-4 h-4 text-orange-500" />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 dark:text-orange-400 ${iconBtn} ${focusRing}`}
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
            <div className={`text-xs space-y-0.5 ${subtle} flex items-center gap-4`}>
              <div>device: <span className={bodyText}>{config.device}</span></div>
              <div>dtype: <span className={bodyText}>{config.dtype}</span></div>
              <div>sr: <span className={bodyText}>{config.sampling_rate} Hz</span></div>
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
