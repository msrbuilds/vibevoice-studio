// Shared TypeScript types matching the backend's Pydantic schemas.

export type VoiceSource = "builtin" | "upload";

export interface EngineLanguage {
  code: string;
  label: string;
}

export type ProjectMode = "tts" | "podcast";

export interface TtsBuffer {
  text: string;
  voiceId: string | null;
  language: string | null;
  // OmniVoice only: per-buffer voice mode + design prompt. Other engines
  // ignore these. Mode is derived when unset (see lib/voiceModes.ts).
  omnivoiceMode?: "clone" | "design" | "auto";
  voiceDesign?: string;
}

export interface Voice {
  id: string;
  name: string;
  gender: string | null;
  language: string | null;
  source: VoiceSource;
  size_bytes: number | null;
  duration_sec: number | null;
  sample_rate: number | null;
  engine: string | null;
  reference_transcript: string | null;
}

export interface VoiceMetadata {
  name?: string;
  gender?: string;
  language?: string;
  reference_transcript?: string;
}

export interface ConfigResponse {
  version: string;
  model_id: string;
  device: string;
  dtype: string;
  attn_implementation: string;
  sampling_rate: number;
  default_cfg_scale: number;
  max_text_chars: number;
  voices_dir: string;
  uploads_dir: string;
  streaming: "planned" | "available" | "unavailable";
  active_engine: string | null;
  engines: EngineInfo[];
}

export interface EngineInfo {
  name: string;
  display_name: string;
  description: string;
  license: string;
  model_url: string;
  loaded: boolean;
  installed: boolean;
  downloaded: boolean;
  supports_voice_cloning: boolean;
  sample_rate: number | null;
  max_speakers: number;
  default_cfg_scale: number | null;
  active: boolean;
  languages: EngineLanguage[];
  supports_voice_modes: boolean;
  supports_style_clone: boolean;
  supports_style_prompt: boolean;
}

export interface InstallStatus {
  state: "not_installed" | "installing" | "installed" | "error";
  log: string[];
  returncode: number | null;
}

export interface DownloadStatus {
  engine: string | null;
  state: "idle" | "downloading" | "done" | "error";
  percent: number | null;
  downloaded_bytes: number;
  total_bytes: number | null;
  speed_bps: number | null;
  eta_sec: number | null;
  current_file: string | null;
  log: string[];
  error: string | null;
  returncode: number | null;
}

export interface DeleteWeightsStatus {
  engine: string | null;
  state: "idle" | "deleting" | "deleted" | "error";
  log: string[];
  error: string | null;
}

export interface UninstallStatus {
  state: "idle" | "uninstalling" | "uninstalled" | "error";
  log: string[];
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "loading" | "error";
  model_loaded: boolean;
  device: string;
  version: string;
}

export interface UploadVoiceResponse {
  id: string;
  name: string;
  size_bytes: number;
  duration_sec: number;
  sample_rate: number;
}

export interface SynthBase64Response {
  audio_b64: string;
  sample_rate: number;
  duration_sec: number;
  inference_ms: number;
}

export interface SynthSpeaker {
  name: string;
  voice: string; // Voice.id (may be empty for OmniVoice design/auto)
  voice_mode?: "clone" | "design" | "auto";
  instruct?: string;
}

// App-level types

export interface Speaker {
  id: string;
  name: string;
  voice: string; // Voice.id
  color: string;
  // OmniVoice only: per-speaker voice mode + design prompt (optional; other
  // engines ignore). Mode is derived when unset — see lib/voiceModes.ts.
  omnivoiceMode?: "clone" | "design" | "auto";
  voiceDesign?: string;
}

export interface Segment {
  id: string;
  text: string;
  speakerId: string | null;
}

export interface CachedAudio {
  audioData: ArrayBuffer;
  text: string;
  voice: string;
  cacheHash?: string;
  // OmniVoice: what mode/prompt produced this, so the cached badge stays honest.
  mode?: "clone" | "design" | "auto";
  instruct?: string;
  // VoxCPM Quality (inference timesteps preset) that produced this clip, so the
  // cache badge re-synths when the user changes Quality. Undefined for engines
  // that don't use it.
  quality?: "fast" | "balanced" | "high";
  // Engine-specific generation signature (Qwen advanced params) — re-synth
  // when it changes. Undefined for engines that don't use it.
  genSig?: string;
}

export interface Project {
  segments: Segment[];
  createdAt: string;
  version: string;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  update_available: boolean;
  html_url: string | null;
  published_at: string | null;
  body: string | null;
  checked_at: number;
  error: string | null;
}

export interface UpdateRunStatus {
  state: "idle" | "running" | "done" | "error";
  log: string[];
  returncode: number | null;
  error: string | null;
}

export interface MemStat {
  used_bytes: number;
  total_bytes: number;
  percent: number;
}

export interface SystemStats {
  cpu_percent: number;
  ram: MemStat;
  vram: MemStat | null;
  disk: MemStat;
  cache_bytes: number;
}
