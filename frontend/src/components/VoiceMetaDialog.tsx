import { useEffect, useState } from "react";
import { Pencil, X } from "lucide-react";
import type { Voice, VoiceMetadata } from "@/types/models";

interface Props {
  voice: Voice | null;
  onClose: () => void;
  onSave: (meta: VoiceMetadata) => Promise<void>;
}

export function VoiceMetaDialog({ voice, onClose, onSave }: Props) {
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"man" | "woman" | "nonbinary" | "">("");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (voice) {
      setName(voice.name);
      setGender((voice.gender as "man" | "woman" | "nonbinary" | null) ?? "");
      setLanguage(voice.language ?? "en");
      setError(null);
    }
  }, [voice]);

  if (!voice) return null;

  const handleSubmit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave({
        name: name.trim() || undefined,
        gender: gender || undefined,
        language: language.trim() || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Pencil className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-semibold text-white">Edit voice</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-zinc-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-xs text-zinc-500 mb-4">
          <code className="text-zinc-400">{voice.id}</code>
          {" · "}
          <span className="capitalize">{voice.source}</span>
        </p>

        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-zinc-400 mb-1 block">Display name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Amelia"
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-teal-500"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1 block">Gender</span>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as typeof gender)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-white focus:outline-none focus:border-teal-500"
              >
                <option value="">—</option>
                <option value="woman">Woman</option>
                <option value="man">Man</option>
                <option value="nonbinary">Non-binary</option>
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-medium text-zinc-400 mb-1 block">Language</span>
              <input
                type="text"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="en"
                maxLength={8}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-teal-500"
              />
            </label>
          </div>
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-400">{error}</p>
        )}

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 text-sm text-zinc-300 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy}
            className="px-4 py-2 text-sm bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
