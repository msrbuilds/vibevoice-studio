import { useState } from "react";
import { Upload, X } from "lucide-react";
import { ApiError, type VoiceMetadata } from "@/lib/api";
import { focusRing } from "@/lib/theme";

interface Props {
  open: boolean;
  theme: "light" | "dark";
  onClose: () => void;
  onUpload: (file: File, meta: VoiceMetadata) => Promise<unknown>;
}

export function UploadVoiceDialog({ open, theme, onClose, onUpload }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"man" | "woman" | "nonbinary" | "">("");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDark = theme === "dark";

  if (!open) return null;

  const reset = () => {
    setFile(null);
    setName("");
    setGender("");
    setLanguage("en");
    setError(null);
  };

  const handleClose = () => {
    if (busy) return;
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("Please choose an audio file");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const meta: VoiceMetadata = {
        name: name.trim() || undefined,
        gender: gender || undefined,
        language: language.trim() || undefined,
      };
      await onUpload(file, meta);
      reset();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const surface = isDark ? "bg-zinc-900" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const text = isDark ? "text-white" : "text-gray-900";
  const labelText = isDark ? "text-zinc-400" : "text-gray-600";
  const subtext = isDark ? "text-zinc-400" : "text-gray-600";
  const inputBg = isDark ? "bg-zinc-800" : "bg-white";
  const inputBorder = isDark ? "border-zinc-700" : "border-gray-300";
  const inputText = isDark ? "text-white" : "text-gray-900";
  const placeholder = isDark ? "placeholder-zinc-500" : "placeholder-gray-400";
  const errorText = "text-red-400";
  const cancelText = isDark ? "text-zinc-300 hover:text-white" : "text-gray-600 hover:text-gray-900";

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/60 p-4"
      onClick={handleClose}
    >
      <div
        className={`${surface} ${border} border rounded-xl shadow-xl w-full max-w-md p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className={`text-lg font-semibold ${text}`}>Upload voice</h2>
          <button
            type="button"
            onClick={handleClose}
            className={`p-1 ${isDark ? "text-zinc-400 hover:text-white" : "text-gray-600 hover:text-gray-900"} ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className={`text-sm mb-4 ${subtext}`}>
          Choose a 1–60 second mono WAV/FLAC/OGG/MP3 clip of a single speaker.
          This audio will be used as the voice identity for generation.
        </p>

        <label className="block">
          <span className={`text-xs font-medium mb-1 block ${labelText}`}>Audio file</span>
          <input
            type="file"
            accept="audio/*,.wav,.flac,.ogg,.mp3"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
            className={`block w-full text-sm text-zinc-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-orange-600 file:text-white hover:file:bg-orange-500 file:cursor-pointer ${focusRing}`}
          />
        </label>

        {file && (
          <p className={`mt-1 text-xs ${subtext}`}>
            {(file.size / 1024).toFixed(1)} KB · {file.name}
          </p>
        )}

        <div className="mt-4 space-y-3">
          <label className="block">
            <span className={`text-xs font-medium mb-1 block ${labelText}`}>Display name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Amelia"
              className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-orange-500`}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className={`text-xs font-medium mb-1 block ${labelText}`}>Gender</span>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as typeof gender)}
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} focus:outline-none focus:border-orange-500`}
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
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-orange-500`}
              />
            </label>
          </div>
        </div>

        {error && (
          <p className={`mt-3 text-sm ${errorText}`}>{error}</p>
        )}

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={busy}
            className={`px-4 py-2 text-sm ${cancelText} ${focusRing}`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy || !file}
            className={`flex items-center gap-2 px-4 py-2 text-sm bg-orange-600 hover:bg-orange-500 disabled:bg-zinc-700 disabled:text-zinc-400 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
          >
            <Upload className="w-4 h-4" />
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
