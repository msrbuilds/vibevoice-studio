import { Plus, Trash2 } from "lucide-react";
import type { Speaker, Voice } from "@/types/models";
import { DESIGN_CHIPS, appendDesignChip, effectiveMode, type OmniMode } from "@/lib/omnivoice";

interface Props {
  speakers: Speaker[];
  voices: Voice[];
  isDark: boolean;
  activeEngine: string | null;
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
  onAddSpeaker,
  onUpdateSpeaker,
  onRemoveSpeaker,
  onSetSpeakerVoice,
}: Props) {
  const heading = isDark ? "text-zinc-500" : "text-gray-500";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-teal-400"
    : "text-gray-400 hover:text-teal-600";

  return (
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
