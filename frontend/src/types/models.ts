// Shared TypeScript types matching the backend's Pydantic schemas.

export type VoiceSource = "builtin" | "upload";

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
}

export interface VoiceMetadata {
  name?: string;
  gender?: string;
  language?: string;
}

export interface ConfigResponse {
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
  loaded: boolean;
  installed: boolean;
  downloaded: boolean;
  supports_voice_cloning: boolean;
  sample_rate: number | null;
  max_speakers: number;
  default_cfg_scale: number | null;
  active: boolean;
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
  voice: string; // Voice.id
}

// App-level types

export interface Speaker {
  id: string;
  name: string;
  voice: string; // Voice.id
  color: string;
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
}

export interface Project {
  segments: Segment[];
  createdAt: string;
  version: string;
}
