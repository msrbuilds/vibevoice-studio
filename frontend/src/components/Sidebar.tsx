import { Mic2, Pencil, Plus, Trash2, Volume2, Waves } from "lucide-react";
import { useState } from "react";
import type { ConfigResponse, Speaker, Voice, VoiceMetadata } from "@/types/models";
import { DESIGN_CHIPS, appendDesignChip, effectiveMode, type OmniMode } from "@/lib/omnivoice";
import { ThemeToggle } from "./ThemeToggle";
import { UploadVoiceDialog } from "./UploadVoiceDialog";
import { VoiceMetaDialog } from "./VoiceMetaDialog";

interface Props {
  speakers: Speaker[];
  voices: Voice[];
  config: ConfigResponse | null;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  onAddSpeaker: () => void;
  onUpdateSpeaker: (id: string, patch: Partial<Speaker>) => void;
  onRemoveSpeaker: (id: string) => void;
  onSetSpeakerVoice: (speakerId: string, voiceId: string) => void;
  onUploadVoice: (file: File, meta: VoiceMetadata) => Promise<unknown>;
  onRemoveVoice: (id: string) => Promise<void>;
  onUpdateVoiceMeta: (voiceId: string, meta: VoiceMetadata) => Promise<unknown>;
  supportsVoiceCloning: boolean;
  activeEngine: string | null;
}

export function Sidebar({
  speakers,
  voices,
  config,
  theme,
  onThemeToggle,
  onAddSpeaker,
  onUpdateSpeaker,
  onRemoveSpeaker,
  onSetSpeakerVoice,
  onUploadVoice,
  onRemoveVoice,
  onUpdateVoiceMeta,
  supportsVoiceCloning,
  activeEngine,
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
      className={`w-80 fixed top-0 left-0 bottom-0 z-10 border-r flex flex-col transition-colors ${surface} ${border}`}
    >
      <div className={`p-5 border-b flex items-center gap-3 ${border}`}>
        <div className="w-9 h-9 rounded-lg bg-teal-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-teal-400" />
        </div>
        <div>
          <h1 className={`font-semibold text-sm ${isDark ? "text-white" : "text-gray-900"}`}>
            VibeVoice Studio
          </h1>
          <p className={`text-xs ${heading}`}>Local · {config?.model_id ?? "—"}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Speakers */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
              Speakers
            </h2>
            <button
              type="button"
              onClick={onAddSpeaker}
              className={`p-1 transition-colors ${iconBtn}`}
              title="Add speaker"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2">
            {speakers.map((sp) => (
              <SpeakerRow
                key={sp.id}
                speaker={sp}
                voices={voices}
                isDark={isDark}
                onUpdate={(patch) => onUpdateSpeaker(sp.id, patch)}
                onRemove={() => onRemoveSpeaker(sp.id)}
                onSetVoice={(v) => onSetSpeakerVoice(sp.id, v)}
                canDelete={speakers.length > 1}
                activeEngine={activeEngine}
              />
            ))}
          </div>
        </section>

        {/* Built-in voices */}
        <section>
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Built-in voices
          </h2>
          <ul className="space-y-1">
            {builtins.map((v) => (
              <li
                key={v.id}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${bodyText} ${hover}`}
              >
                <Volume2 className={`w-4 h-4 ${subtle}`} />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={() => setEditingVoice(v)}
                  className={`p-1 ${iconBtn}`}
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
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
            {uploads.map((v) => (
              <li
                key={v.id}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${bodyText} ${hover}`}
              >
                <Mic2 className="w-4 h-4 text-teal-500" />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && <span className={`text-xs ${subtle}`}>{v.gender}</span>}
                <button
                  type="button"
                  onClick={() => setEditingVoice(v)}
                  className={`p-1 ${iconBtn}`}
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveVoice(v.id)}
                  className={`p-1 ${danger}`}
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
            {uploads.length === 0 && (
              <li className={`text-xs italic px-2 py-1.5 ${empty}`}>
                Click + to upload a voice.
              </li>
            )}
          </ul>
        </section>
        )}
      </div>

      <div className={`p-4 border-t space-y-2 ${border}`}>
        {config && (
          <div className={`text-xs space-y-0.5 ${subtle} flex items-center gap-4`}>
            <div>device: <span className={bodyText}>{config.device}</span></div>
            <div>dtype: <span className={bodyText}>{config.dtype}</span></div>
            <div>sr: <span className={bodyText}>{config.sampling_rate} Hz</span></div>
          </div>
        )}
        <ThemeToggle theme={theme} onToggle={onThemeToggle} />
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

function SpeakerRow({
  speaker,
  voices,
  isDark,
  onUpdate,
  onRemove,
  onSetVoice,
  canDelete,
  activeEngine,
}: {
  speaker: Speaker;
  voices: Voice[];
  isDark: boolean;
  onUpdate: (patch: Partial<Speaker>) => void;
  onRemove: () => void;
  onSetVoice: (v: string) => void;
  canDelete: boolean;
  activeEngine: string | null;
}) {
  const panelBg = isDark ? "bg-zinc-900/50" : "bg-gray-50";
  const panelBorder = isDark ? "border-zinc-800" : "border-gray-200";
  const inputText = isDark ? "text-white" : "text-gray-900";
  const selectBg = isDark ? "bg-zinc-800" : "bg-white";
  const selectBorder = isDark ? "border-zinc-700" : "border-gray-300";
  const selectText = isDark ? "text-white" : "text-gray-900";
  const danger = isDark
    ? "text-zinc-500 hover:text-red-400"
    : "text-gray-400 hover:text-red-600";

  const nameHeader = (
    <div className="flex items-center gap-2 mb-2">
      <span
        className="w-3 h-3 rounded-full shrink-0"
        style={{ backgroundColor: speaker.color }}
      />
      <input
        type="text"
        value={speaker.name}
        onChange={(e) => onUpdate({ name: e.target.value })}
        className={`flex-1 bg-transparent text-sm font-medium focus:outline-none focus:ring-1 focus:ring-teal-500/50 rounded px-1 ${inputText}`}
      />
      {canDelete && (
        <button
          type="button"
          onClick={onRemove}
          className={`p-1 ${danger}`}
          title="Delete speaker"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );

  const voiceSelect = (
    <select
      value={speaker.voice}
      onChange={(e) => onSetVoice(e.target.value)}
      className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg} ${selectBorder} ${selectText}`}
    >
      <option value="">Select voice…</option>
      {voices.map((v) => (
        <option key={v.id} value={v.id}>
          {v.name} {v.source === "upload" ? "(mine)" : ""}
        </option>
      ))}
    </select>
  );

  const isOmni = activeEngine === "omnivoice";
  const mode: OmniMode = effectiveMode(speaker);
  const setMode = (m: OmniMode) => onUpdate({ omnivoiceMode: m });

  if (!isOmni) {
    return (
      <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
        {nameHeader}
        {voiceSelect}
      </div>
    );
  }

  const segBtn = (m: OmniMode, label: string) => (
    <button
      type="button"
      onClick={() => setMode(m)}
      className={`flex-1 px-2 py-1 text-[11px] font-medium rounded transition-colors ${
        mode === m
          ? "bg-teal-600 text-white"
          : isDark
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className={`p-3 rounded-lg border ${panelBg} ${panelBorder}`}>
      {nameHeader}
      <div className="flex gap-1 mb-2">
        {segBtn("clone", "Clone")}
        {segBtn("design", "Design")}
        {segBtn("auto", "Auto")}
      </div>
      {mode === "clone" && voiceSelect}
      {mode === "design" && (
        <div className="space-y-1.5">
          <input
            type="text"
            value={speaker.voiceDesign ?? ""}
            onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
            placeholder="e.g. female, low pitch, british accent, warm"
            className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg} ${selectBorder} ${selectText}`}
          />
          <div className="flex flex-wrap gap-1">
            {DESIGN_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onUpdate({ voiceDesign: appendDesignChip(speaker.voiceDesign ?? "", chip) })}
                className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
                  isDark
                    ? "border-zinc-700 text-zinc-400 hover:border-teal-500 hover:text-teal-300"
                    : "border-gray-300 text-gray-500 hover:border-teal-500 hover:text-teal-600"
                }`}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      )}
      {mode === "auto" && (
        <p className={`text-[11px] italic ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
          OmniVoice will invent a voice for this speaker.
        </p>
      )}
    </div>
  );
}
