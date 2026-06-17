import { useState } from "react";
import { Upload, X } from "lucide-react";
import { ApiError, type VoiceMetadata } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onUpload: (file: File, meta: VoiceMetadata) => Promise<unknown>;
}

export function UploadVoiceDialog({ open, onClose, onUpload }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"man" | "woman" | "nonbinary" | "">("");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/60 p-4"
      onClick={handleClose}
    >
      <div
        className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Upload voice</h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 text-zinc-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-zinc-400 mb-4">
          Choose a 1–60 second mono WAV/FLAC/OGG/MP3 clip of a single speaker.
          This audio will be used as the voice identity for generation.
        </p>

        <label className="block">
          <span className="text-xs font-medium text-zinc-400 mb-1 block">Audio file</span>
          <input
            type="file"
            accept="audio/*,.wav,.flac,.ogg,.mp3"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
            className="block w-full text-sm text-zinc-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-teal-600 file:text-white hover:file:bg-teal-500 file:cursor-pointer"
          />
        </label>

        {file && (
          <p className="mt-1 text-xs text-zinc-500">
            {(file.size / 1024).toFixed(1)} KB · {file.name}
          </p>
        )}

        <div className="mt-4 space-y-3">
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
            onClick={handleClose}
            disabled={busy}
            className="px-4 py-2 text-sm text-zinc-300 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy || !file}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
          >
            <Upload className="w-4 h-4" />
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
