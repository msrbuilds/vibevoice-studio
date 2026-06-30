import { Plus, Trash2 } from "lucide-react";
import type { Speaker, Voice } from "@/types/models";
import { DESIGN_CHIPS, appendDesignChip, effectiveMode, type OmniMode } from "@/lib/voiceModes";
import { focusRing } from "@/lib/theme";

interface Props {
  speakers: Speaker[];
  voices: Voice[];
  isDark: boolean;
  activeEngine: string | null;
  supportsVoiceModes: boolean;
  supportsStyleClone: boolean;
  onAddSpeaker: () => void;
  onUpdateSpeaker: (id: string, patch: Partial<Speaker>) => void;
  onRemoveSpeaker: (id: string) => void;
  onSetSpeakerVoice: (speakerId: string, voiceId: string) => void;
}

export function SpeakerRoster({
  speakers,
  voices,
  isDark,
  activeEngine,
  supportsVoiceModes,
  supportsStyleClone,
  onAddSpeaker,
  onUpdateSpeaker,
  onRemoveSpeaker,
  onSetSpeakerVoice,
}: Props) {
  const heading = isDark ? "text-zinc-400" : "text-gray-600";


  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
          Speakers
        </h2>
        <button
          type="button"
          onClick={onAddSpeaker}
          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${focusRing} ${
            isDark
              ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700"
              : "bg-white hover:bg-gray-100 text-gray-700 hover:text-gray-900 border border-gray-300"
          }`}
          title="Add speaker"
        >
          <Plus className="w-3.5 h-3.5" />
          Add
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
            supportsVoiceModes={supportsVoiceModes}
            supportsStyleClone={supportsStyleClone}
          />
        ))}
      </div>
    </section>
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
  supportsVoiceModes,
  supportsStyleClone,
}: {
  speaker: Speaker;
  voices: Voice[];
  isDark: boolean;
  onUpdate: (patch: Partial<Speaker>) => void;
  onRemove: () => void;
  onSetVoice: (v: string) => void;
  canDelete: boolean;
  activeEngine: string | null;
  supportsVoiceModes: boolean;
  supportsStyleClone: boolean;
}) {
  const panelBg = isDark ? "bg-zinc-900/50" : "bg-gray-50";
  const panelBorder = isDark ? "border-zinc-800" : "border-gray-200";
  const inputText = isDark ? "text-white" : "text-gray-900";
  const selectBg = isDark ? "bg-zinc-800" : "bg-white";
  const selectBorder = isDark ? "border-zinc-700" : "border-gray-300";
  const selectText = isDark ? "text-white" : "text-gray-900";
  const danger = isDark
    ? "text-zinc-400 hover:text-red-400"
    : "text-gray-600 hover:text-red-700";

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
        className={`flex-1 bg-transparent text-sm font-medium focus:outline-none focus:border-b focus:border-orange-500 rounded px-1 ${inputText}`}
      />
      {canDelete && (
        <button
          type="button"
          onClick={onRemove}
          className={`p-1 ${danger} ${focusRing}`}
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
      className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
    >
      <option value="">Select voice…</option>
      {voices.map((v) => (
        <option key={v.id} value={v.id}>
          {v.name} {v.source === "upload" ? "(mine)" : ""}
        </option>
      ))}
    </select>
  );

  const showModes = supportsVoiceModes;
  const mode: OmniMode = effectiveMode(speaker);
  const setMode = (m: OmniMode) => onUpdate({ omnivoiceMode: m });

  if (!showModes) {
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
      className={`flex-1 px-2 py-2 text-[14px] font-medium rounded transition-colors border ${
        mode === m
          ? "bg-orange-600 text-white border-orange-500 hover:bg-orange-500"
          : isDark
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border-zinc-700 hover:text-white"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      } ${focusRing}`}
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
      {mode === "clone" && (
        <div className="space-y-1.5">
          {voiceSelect}
          {supportsStyleClone && (
            <input
              type="text"
              value={speaker.voiceDesign ?? ""}
              onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
              placeholder="Style (optional) — e.g. cheerful, slightly faster"
              className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
            />
          )}
        </div>
      )}
      {mode === "design" && (
        <div className="space-y-1.5">
          <input
            type="text"
            value={speaker.voiceDesign ?? ""}
            onChange={(e) => onUpdate({ voiceDesign: e.target.value })}
            placeholder={activeEngine === "voxcpm" ? "e.g. a young woman, gentle and sweet" : "e.g. female, low pitch, british accent"}
            className={`w-full border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-orange-500 ${selectBg} ${selectBorder} ${selectText}`}
          />
          {activeEngine === "omnivoice" && (
            <div className="flex flex-wrap gap-1">
              {DESIGN_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => onUpdate({ voiceDesign: appendDesignChip(speaker.voiceDesign ?? "", chip) })}
                  className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
                    isDark
                      ? "border-zinc-700 text-zinc-400 hover:border-orange-500 hover:text-orange-300"
                      : "border-gray-300 text-gray-600 hover:border-orange-500 hover:text-orange-600"
                  } ${focusRing}`}
                >
                  {chip}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {mode === "auto" && (
        <p className={`text-[11px] italic ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
          {activeEngine === "voxcpm"
            ? "VoxCPM will design a fresh voice for this speaker."
            : "OmniVoice will invent a voice for this speaker."}
        </p>
      )}
    </div>
  );
}
