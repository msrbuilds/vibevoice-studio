import { Mic2, Pencil, Plus, Trash2, Volume2, Waves } from "lucide-react";
import { useState } from "react";
import type { ConfigResponse, Voice, VoiceMetadata } from "@/types/models";
import { UploadVoiceDialog } from "./UploadVoiceDialog";
import { VoiceMetaDialog } from "./VoiceMetaDialog";
import { ThemeToggle } from "./ThemeToggle";

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
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editingVoice, setEditingVoice] = useState<Voice | null>(null);

  const builtins = voices.filter((v) => v.source === "builtin");
  const uploads = voices.filter((v) => v.source === "upload");

  const isDark = theme === "dark";
  // Surface tokens — the sidebar has its own palette in both themes so it
  // reads as a distinct panel from the main content.
  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-500" : "text-gray-500";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const subtle = isDark ? "text-zinc-500" : "text-gray-500";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-teal-400"
    : "text-gray-400 hover:text-teal-600";
  const hover = isDark ? "hover:bg-zinc-900" : "hover:bg-gray-100";
  const danger = isDark
    ? "text-zinc-500 hover:text-red-400"
    : "text-gray-400 hover:text-red-600";
  const empty = isDark ? "text-zinc-600" : "text-gray-400";

  return (
    <aside
      className={`w-80 shrink-0 z-10 border-r flex flex-col transition-colors ${surface} ${border}`}
    >
      <div className={`p-5 border-b flex items-center gap-3 ${border}`}>
        <div className="w-9 h-9 rounded-lg bg-teal-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-teal-400" />
        </div>
        <div>
          <h1 className={`font-semibold text-sm ${isDark ? "text-white" : "text-gray-900"}`}>
            Voice Studio by MSR
          </h1>
          <p className={`text-xs ${heading}`}>Local · {config?.model_id ?? "—"}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Built-in voices */}
        <section>
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
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${bodyText} ${hover} ${
                  onSelectVoice ? "cursor-pointer" : ""
                } ${isSelected ? "ring-1 ring-teal-500 bg-teal-600/10" : ""}`}
              >
                <Volume2 className={`w-4 h-4 ${subtle}`} />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 ${iconBtn}`}
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
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
              My voices
            </h2>
            <button
              type="button"
              onClick={() => setUploadOpen(true)}
              className={`p-1 transition-colors ${iconBtn}`}
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
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${bodyText} ${hover} ${
                  onSelectVoice ? "cursor-pointer" : ""
                } ${isSelected ? "ring-1 ring-teal-500 bg-teal-600/10" : ""}`}
              >
                <Mic2 className="w-4 h-4 text-teal-500" />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setEditingVoice(v); }}
                  className={`p-1 ${iconBtn}`}
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); void onRemoveVoice(v.id); }}
                  className={`p-1 ${danger}`}
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
