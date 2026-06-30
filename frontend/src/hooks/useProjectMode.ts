import { useCallback, useEffect, useState } from "react";
import type { ProjectMode, TtsBuffer } from "@/types/models";

const MODE_KEY = "vs.mode";
const TTS_KEY = "vs.tts";
const EMPTY_TTS: TtsBuffer = { text: "", voiceId: null, language: null };

function readMode(): ProjectMode | null {
  const v = localStorage.getItem(MODE_KEY);
  return v === "tts" || v === "podcast" ? v : null;
}
function readTts(): TtsBuffer {
  try {
    const raw = localStorage.getItem(TTS_KEY);
    if (!raw) return EMPTY_TTS;
    const p = JSON.parse(raw) as Partial<TtsBuffer>;
    return {
      text: p.text ?? "",
      voiceId: p.voiceId ?? null,
      language: p.language ?? null,
      omnivoiceMode: p.omnivoiceMode,
      voiceDesign: p.voiceDesign,
    };
  } catch {
    return EMPTY_TTS;
  }
}

export interface UseProjectModeApi {
  mode: ProjectMode | null;
  setMode: (m: ProjectMode) => void;
  tts: TtsBuffer;
  setTtsText: (text: string) => void;
  setTtsVoice: (voiceId: string | null) => void;
  setTtsLanguage: (language: string | null) => void;
  setTtsOmniMode: (mode: "clone" | "design" | "auto" | "custom") => void;
  setTtsVoiceDesign: (voiceDesign: string) => void;
}

export function useProjectMode(): UseProjectModeApi {
  const [mode, setModeState] = useState<ProjectMode | null>(readMode);
  const [tts, setTts] = useState<TtsBuffer>(readTts);

  useEffect(() => {
    if (mode) localStorage.setItem(MODE_KEY, mode);
  }, [mode]);
  useEffect(() => {
    localStorage.setItem(TTS_KEY, JSON.stringify(tts));
  }, [tts]);

  const setMode = useCallback((m: ProjectMode) => setModeState(m), []);
  const setTtsText = useCallback((text: string) => setTts((t) => ({ ...t, text })), []);
  const setTtsVoice = useCallback((voiceId: string | null) => setTts((t) => ({ ...t, voiceId })), []);
  const setTtsLanguage = useCallback((language: string | null) => setTts((t) => ({ ...t, language })), []);
  const setTtsOmniMode = useCallback(
    (omnivoiceMode: "clone" | "design" | "auto" | "custom") => setTts((t) => ({ ...t, omnivoiceMode })),
    [],
  );
  const setTtsVoiceDesign = useCallback(
    (voiceDesign: string) => setTts((t) => ({ ...t, voiceDesign })),
    [],
  );

  return {
    mode,
    setMode,
    tts,
    setTtsText,
    setTtsVoice,
    setTtsLanguage,
    setTtsOmniMode,
    setTtsVoiceDesign,
  };
}
