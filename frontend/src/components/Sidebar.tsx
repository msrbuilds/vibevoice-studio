import { Mic2, Pencil, Plus, Trash2, Volume2, Waves } from "lucide-react";
import { useState } from "react";
import type { ConfigResponse, Speaker, Voice, VoiceMetadata } from "@/types/models";
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
}: Props) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editingVoice, setEditingVoice] = useState<Voice | null>(null);

  const builtins = voices.filter((v) => v.source === "builtin");
  const uploads = voices.filter((v) => v.source === "upload");

  return (
    <aside
      className="w-80 fixed top-0 left-0 bottom-0 z-10 border-r flex flex-col
        bg-zinc-950 border-zinc-800"
    >
      <div className="p-5 border-b border-zinc-800 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-teal-600/20 flex items-center justify-center">
          <Waves className="w-5 h-5 text-teal-400" />
        </div>
        <div>
          <h1 className="font-semibold text-white text-sm">VibeVoice Studio</h1>
          <p className="text-xs text-zinc-500">Local · {config?.model_id ?? "—"}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Speakers */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Speakers
            </h2>
            <button
              type="button"
              onClick={onAddSpeaker}
              className="p-1 text-zinc-400 hover:text-teal-400 transition-colors"
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
                onUpdate={(patch) => onUpdateSpeaker(sp.id, patch)}
                onRemove={() => onRemoveSpeaker(sp.id)}
                onSetVoice={(v) => onSetSpeakerVoice(sp.id, v)}
                canDelete={speakers.length > 1}
              />
            ))}
          </div>
        </section>

        {/* Built-in voices */}
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">
            Built-in voices
          </h2>
          <ul className="space-y-1">
            {builtins.map((v) => (
              <li
                key={v.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-zinc-300"
              >
                <Volume2 className="w-4 h-4 text-zinc-500" />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && (
                  <span className="text-xs text-zinc-500">{v.gender}</span>
                )}
                <button
                  type="button"
                  onClick={() => setEditingVoice(v)}
                  className="p-1 text-zinc-500 hover:text-teal-400"
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
            {builtins.length === 0 && (
              <li className="text-xs text-zinc-600 italic px-2 py-1.5">
                No built-in voices. Drop .wav files into backend/voices/.
              </li>
            )}
          </ul>
        </section>

        {/* User uploads */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              My voices
            </h2>
            <button
              type="button"
              onClick={() => setUploadOpen(true)}
              className="p-1 text-zinc-400 hover:text-teal-400 transition-colors"
              title="Upload voice"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <ul className="space-y-1">
            {uploads.map((v) => (
              <li
                key={v.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-zinc-300 hover:bg-zinc-900"
              >
                <Mic2 className="w-4 h-4 text-teal-500" />
                <span className="flex-1 truncate">{v.name}</span>
                {v.gender && (
                  <span className="text-xs text-zinc-500">{v.gender}</span>
                )}
                <button
                  type="button"
                  onClick={() => setEditingVoice(v)}
                  className="p-1 text-zinc-500 hover:text-teal-400"
                  title="Edit name / gender / language"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveVoice(v.id)}
                  className="p-1 text-zinc-500 hover:text-red-400"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
            {uploads.length === 0 && (
              <li className="text-xs text-zinc-600 italic px-2 py-1.5">
                Click + to upload a voice.
              </li>
            )}
          </ul>
        </section>
      </div>

      <div className="p-4 border-t border-zinc-800 space-y-2">
        {config && (
          <div className="text-xs text-zinc-500 space-y-0.5">
            <div>device: <span className="text-zinc-300">{config.device}</span></div>
            <div>dtype: <span className="text-zinc-300">{config.dtype}</span></div>
            <div>sr: <span className="text-zinc-300">{config.sampling_rate} Hz</span></div>
          </div>
        )}
        <ThemeToggle theme={theme} onToggle={onThemeToggle} />
      </div>

      <UploadVoiceDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUpload={onUploadVoice}
      />

      <VoiceMetaDialog
        voice={editingVoice}
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
  onUpdate,
  onRemove,
  onSetVoice,
  canDelete,
}: {
  speaker: Speaker;
  voices: Voice[];
  onUpdate: (patch: Partial<Speaker>) => void;
  onRemove: () => void;
  onSetVoice: (v: string) => void;
  canDelete: boolean;
}) {
  return (
    <div className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: speaker.color }}
        />
        <input
          type="text"
          value={speaker.name}
          onChange={(e) => onUpdate({ name: e.target.value })}
          className="flex-1 bg-transparent text-sm text-white font-medium focus:outline-none focus:ring-1 focus:ring-teal-500/50 rounded px-1"
        />
        {canDelete && (
          <button
            type="button"
            onClick={onRemove}
            className="p-1 text-zinc-500 hover:text-red-400"
            title="Delete speaker"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <select
        value={speaker.voice}
        onChange={(e) => onSetVoice(e.target.value)}
        className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-teal-500"
      >
        <option value="">Select voice…</option>
        {voices.map((v) => (
          <option key={v.id} value={v.id}>
            {v.name} {v.source === "upload" ? "(mine)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
