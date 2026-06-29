import { useEffect, useState } from "react";
import { Pencil, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import type { Voice, VoiceMetadata } from "@/types/models";

interface Props {
  voice: Voice | null;
  theme: "light" | "dark";
  onClose: () => void;
  onSave: (meta: VoiceMetadata) => Promise<void>;
}

export function VoiceMetaDialog({ voice, theme, onClose, onSave }: Props) {
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"man" | "woman" | "nonbinary" | "">("");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDark = theme === "dark";

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

  const surface = isDark ? "bg-zinc-900" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const text = isDark ? "text-white" : "text-gray-900";
  const labelText = isDark ? "text-zinc-400" : "text-gray-600";
  const subtext = isDark ? "text-zinc-400" : "text-gray-600";
  const idColor = isDark ? "text-zinc-400" : "text-gray-700";
  const inputBg = isDark ? "bg-zinc-800" : "bg-white";
  const inputBorder = isDark ? "border-zinc-700" : "border-gray-300";
  const inputText = isDark ? "text-white" : "text-gray-900";
  const placeholder = isDark ? "placeholder-zinc-500" : "placeholder-gray-400";
  const cancelText = isDark ? "text-zinc-300 hover:text-white" : "text-gray-600 hover:text-gray-900";

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className={`${surface} ${border} border rounded-xl shadow-xl w-full max-w-md p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Pencil className="w-5 h-5 text-teal-400" />
            <h2 className={`text-lg font-semibold ${text}`}>Edit voice</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`p-1 ${isDark ? "text-zinc-400 hover:text-white" : "text-gray-600 hover:text-gray-900"} ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className={`text-xs mb-4 ${subtext}`}>
          <code className={idColor}>{voice.id}</code>
          {" · "}
          <span className="capitalize">{voice.source}</span>
        </p>

        <div className="space-y-3">
          <label className="block">
            <span className={`text-xs font-medium mb-1 block ${labelText}`}>Display name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Amelia"
              className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-teal-500 ${focusRing}`}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className={`text-xs font-medium mb-1 block ${labelText}`}>Gender</span>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as typeof gender)}
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} focus:outline-none focus:border-teal-500 ${focusRing}`}
              >
                <option value="">—</option>
                <option value="woman">Woman</option>
                <option value="man">Man</option>
                <option value="nonbinary">Non-binary</option>
              </select>
            </label>
            <label className="block">
              <span className={`text-xs font-medium mb-1 block ${labelText}`}>Language</span>
              <input
                type="text"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="en"
                maxLength={8}
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-teal-500 ${focusRing}`}
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
            className={`px-4 py-2 text-sm ${cancelText} ${focusRing}`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy}
            className={`px-4 py-2 text-sm bg-teal-700 hover:bg-teal-600 disabled:bg-zinc-700 disabled:text-zinc-400 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
