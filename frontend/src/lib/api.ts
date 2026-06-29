// Typed wrappers for the backend's REST API.

import type {
  ConfigResponse,
  DownloadStatus,
  EngineInfo,
  HealthResponse,
  InstallStatus,
  SynthBase64Response,
  SynthSpeaker,
  UploadVoiceResponse,
  Voice,
} from "@/types/models";

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as {
        detail?: string | Array<{ msg?: string; loc?: unknown[] }>;
        code?: string;
      };
      if (body.detail) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          // FastAPI validation error: array of {loc, msg, type}
          detail = body.detail
            .map((d) => (d.loc?.slice(-1)?.[0] ? `${d.loc.slice(-1)[0]}: ${d.msg}` : d.msg ?? ""))
            .filter(Boolean)
            .join("; ") || detail;
        } else {
          detail = String(body.detail);
        }
      }
    } catch {
      // ignore JSON parse errors; fall through with statusText
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function getConfig(): Promise<ConfigResponse> {
  return jsonOrThrow<ConfigResponse>(await fetch(`${API_BASE}/config`));
}

export interface CacheEntryInfo {
  hash: string;
  sample_rate: number;
  duration_sec: number;
  inference_ms: number;
  size_bytes: number;
  created_at: number;
  text: string | null;
  voice: string | null;
  name: string;
}

export interface CacheListResponse {
  enabled: boolean;
  directory: string;
  entry_count: number;
  max_entries: number;
  entries: CacheEntryInfo[];
}

export async function listCache(): Promise<CacheListResponse> {
  return jsonOrThrow<CacheListResponse>(await fetch(`${API_BASE}/cache`));
}

export async function clearCache(): Promise<{ removed: number }> {
  return jsonOrThrow<{ removed: number }>(
    await fetch(`${API_BASE}/cache`, { method: "DELETE" }),
  );
}

export async function deleteCacheEntry(hash: string): Promise<{ deleted: string }> {
  return jsonOrThrow<{ deleted: string }>(
    await fetch(`${API_BASE}/cache/${encodeURIComponent(hash)}`, { method: "DELETE" }),
  );
}

/** Returns the relative URL for streaming a cached clip's WAV. */
export function cacheAudioUrl(hash: string): string {
  return `/api/cache/${hash}/audio`;
}

/** Ask the local backend to open the cache directory in the OS file manager. */
export async function openCacheFolder(): Promise<{ opened: string }> {
  return jsonOrThrow<{ opened: string }>(
    await fetch(`${API_BASE}/cache/folder`, { method: "POST" }),
  );
}

export async function getHealth(): Promise<HealthResponse> {
  return jsonOrThrow<HealthResponse>(await fetch(`${API_BASE}/health`));
}

export async function listVoices(): Promise<Voice[]> {
  const data = await jsonOrThrow<{ voices: Voice[] }>(
    await fetch(`${API_BASE}/voices`),
  );
  return data.voices;
}

export interface VoiceMetadata {
  name?: string;
  gender?: string;
  language?: string;
}

export interface EngineListResponse {
  active: string;
  engines: EngineInfo[];
}

export async function listEngines(): Promise<EngineListResponse> {
  return jsonOrThrow<EngineListResponse>(
    await fetch(`${API_BASE}/engines`),
  );
}

export async function activateEngine(name: string): Promise<EngineInfo> {
  return jsonOrThrow<EngineInfo>(
    await fetch(`${API_BASE}/engines/activate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  );
}

export async function loadEngine(name: string): Promise<EngineInfo> {
  return jsonOrThrow<EngineInfo>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/load`, {
      method: "POST",
    }),
  );
}

export async function startEngineInstall(name: string): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/install`, { method: "POST" }),
  );
}

export async function getEngineInstallStatus(name: string): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/install`),
  );
}

export async function startModelDownload(name: string): Promise<DownloadStatus> {
  return jsonOrThrow<DownloadStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/download`, {
      method: "POST",
    }),
  );
}

export async function getModelDownloadStatus(name: string): Promise<DownloadStatus> {
  return jsonOrThrow<DownloadStatus>(
    await fetch(`${API_BASE}/engines/${encodeURIComponent(name)}/download`),
  );
}

export async function uploadVoice(
  file: File,
  meta: VoiceMetadata = {},
): Promise<UploadVoiceResponse> {
  const fd = new FormData();
  fd.append("file", file);
  if (meta.name) fd.append("name", meta.name);
  if (meta.gender) fd.append("gender", meta.gender);
  if (meta.language) fd.append("language", meta.language);
  return jsonOrThrow<UploadVoiceResponse>(
    await fetch(`${API_BASE}/voices/upload`, { method: "POST", body: fd }),
  );
}

export async function updateVoiceMeta(
  voiceId: string,
  meta: VoiceMetadata,
): Promise<Voice> {
  return jsonOrThrow<Voice>(
    await fetch(`${API_BASE}/voices/${encodeURIComponent(voiceId)}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(meta),
    }),
  );
}

export async function editBuiltInVoice(
  voiceId: string,
  meta: VoiceMetadata,
): Promise<Voice> {
  return jsonOrThrow<Voice>(
    await fetch(`${API_BASE}/voices/${encodeURIComponent(voiceId)}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(meta),
    }),
  );
}

export async function deleteVoice(voiceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/voices/${encodeURIComponent(voiceId)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    await jsonOrThrow(res); // throws ApiError
  }
}

/**
 * Synthesize text → speech, returning the WAV bytes as an ArrayBuffer.
 * Backend may return either audio/wav (default) or JSON (response_format=base64).
 *
 * @param text       Script text. If it doesn't contain `Speaker N:` lines, the
 *                   backend wraps it as a single-speaker script using speakers[0].
 * @param speakers   Ordered list of speakers in the script. Each entry has a
 *                   `name` (used in `Speaker <name>: ...` tags after normalization)
 *                   and a `voice` (Voice.id to use for that speaker's reference audio).
 */
export async function synthesizeWav(
  text: string,
  speakers: SynthSpeaker[],
  cfgScale?: number,
  options: {
    forceRegenerate?: boolean;
    cfgWeight?: number | null;
    exaggeration?: number | null;
    languageId?: string | null;
  } = {},
): Promise<{ audioData: ArrayBuffer; sampleRate: number; durationSec: number; inferenceMs: number; cacheHit: boolean; cacheHash: string | null }> {
  const res = await fetch(`${API_BASE}/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      speakers,
      ...(cfgScale !== undefined ? { cfg_scale: cfgScale } : {}),
      ...(options.cfgWeight != null ? { cfg_weight: options.cfgWeight } : {}),
      ...(options.exaggeration != null ? { exaggeration: options.exaggeration } : {}),
      ...(options.languageId ? { language_id: options.languageId } : {}),
      ...(options.forceRegenerate ? { force_regenerate: true } : {}),
    }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string; code?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await res.json()) as SynthBase64Response;
    const binary = atob(payload.audio_b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return {
      audioData: bytes.buffer,
      sampleRate: payload.sample_rate,
      durationSec: payload.duration_sec,
      inferenceMs: payload.inference_ms,
      cacheHit: res.headers.get("X-Cache") === "hit",
      cacheHash: res.headers.get("X-Cache-Hash"),
    };
  }

  const audioData = await res.arrayBuffer();
  const sampleRate = Number(res.headers.get("X-Sample-Rate") ?? "24000");
  const durationSec = Number(res.headers.get("X-Audio-Duration-Sec") ?? "0");
  const inferenceMs = Number(res.headers.get("X-Inference-Ms") ?? "0");
  return {
    audioData,
    sampleRate,
    durationSec,
    inferenceMs,
    cacheHit: res.headers.get("X-Cache") === "hit",
    cacheHash: res.headers.get("X-Cache-Hash"),
  };
}

export interface DownloadSegmentPayload {
  text: string;
  voice: string;
  cfg_scale?: number;
  cache_hash?: string;
  cfg_weight?: number;
  exaggeration?: number;
  language_id?: string;
  voice_mode?: "clone" | "design" | "auto";
  instruct?: string;
}

export async function downloadPodcast(
  segments: DownloadSegmentPayload[],
  silenceGapMs = 150,
): Promise<{ audioData: ArrayBuffer; sampleRate: number; durationSec: number; cacheHit: boolean; cacheHash: string | null }> {
  const res = await fetch(`${API_BASE}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments, silence_gap_ms: silenceGapMs }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string; code?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }
  const audioData = await res.arrayBuffer();
  return {
    audioData,
    sampleRate: Number(res.headers.get("X-Sample-Rate") ?? "24000"),
    durationSec: Number(res.headers.get("X-Audio-Duration-Sec") ?? "0"),
    cacheHit: res.headers.get("X-Cache") === "hit",
    cacheHash: res.headers.get("X-Cache-Hash"),
  };
}
