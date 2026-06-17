// useProject: reducer-based hook for the editing state (segments + speakers).

import { useCallback, useMemo, useReducer } from "react";
import type { CachedAudio, Project, Segment, Speaker } from "@/types/models";

const SPEAKER_COLORS = [
  "#3b82f6", // blue
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

const INITIAL_SPEAKER: Speaker = {
  id: "host-1",
  name: "Host",
  voice: "",
  color: SPEAKER_COLORS[0]!,
};

const INITIAL_SEGMENT: Segment = {
  id: crypto.randomUUID(),
  text: "Welcome to our podcast! Today we'll be discussing exciting topics.",
  speakerId: INITIAL_SPEAKER.id,
};

interface State {
  segments: Segment[];
  speakers: Speaker[];
  audioCache: Record<string, CachedAudio>;
}

type Action =
  | { type: "add_segment"; segment: Segment }
  | { type: "remove_segment"; id: string }
  | { type: "update_segment"; id: string; field: "text" | "speakerId"; value: string }
  | { type: "add_speaker"; speaker: Speaker }
  | { type: "update_speaker"; id: string; patch: Partial<Speaker> }
  | { type: "remove_speaker"; id: string }
  | { type: "set_voice"; speakerId: string; voice: string }
  | { type: "cache_audio"; id: string; entry: CachedAudio }
  | { type: "invalidate_cache"; id: string }
  | { type: "clear_cache" }
  | { type: "load_project"; project: Project; speakers: Speaker[] };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "add_segment":
      return { ...state, segments: [...state.segments, action.segment] };

    case "remove_segment":
      if (state.segments.length <= 1) return state;
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [action.id]: _, ...remaining } = state.audioCache;
      return {
        ...state,
        segments: state.segments.filter((s) => s.id !== action.id),
        audioCache: remaining,
      };

    case "update_segment":
      return {
        ...state,
        segments: state.segments.map((s) =>
          s.id === action.id ? { ...s, [action.field]: action.value } : s,
        ),
        audioCache: action.field === "text" ? invalidateKey(state.audioCache, action.id) : state.audioCache,
      };

    case "add_speaker":
      return { ...state, speakers: [...state.speakers, action.speaker] };

    case "update_speaker":
      return {
        ...state,
        speakers: state.speakers.map((s) =>
          s.id === action.id ? { ...s, ...action.patch } : s,
        ),
      };

    case "remove_speaker":
      if (state.speakers.length <= 1) return state;
      return {
        ...state,
        speakers: state.speakers.filter((s) => s.id !== action.id),
        segments: state.segments.map((seg) =>
          seg.speakerId === action.id ? { ...seg, speakerId: null } : seg,
        ),
      };

    case "set_voice":
      return {
        ...state,
        speakers: state.speakers.map((s) =>
          s.id === action.speakerId ? { ...s, voice: action.voice } : s,
        ),
        // No cache invalidation here; segments pick up the new voice lazily.
      };

    case "cache_audio":
      return {
        ...state,
        audioCache: { ...state.audioCache, [action.id]: action.entry },
      };

    case "invalidate_cache":
      return { ...state, audioCache: invalidateKey(state.audioCache, action.id) };

    case "load_project":
      return {
        segments: action.project.segments,
        speakers: action.speakers,
        audioCache: {},
      };

    default:
      return state;
  }
}

function invalidateKey(cache: Record<string, CachedAudio>, id: string): Record<string, CachedAudio> {
  if (!(id in cache)) return cache;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { [id]: _, ...rest } = cache;
  return rest;
}

const INITIAL_STATE: State = {
  segments: [INITIAL_SEGMENT],
  speakers: [INITIAL_SPEAKER],
  audioCache: {},
};

export interface UseProjectApi {
  segments: Segment[];
  speakers: Speaker[];
  audioCache: Record<string, CachedAudio>;
  addSegment: () => void;
  removeSegment: (id: string) => void;
  updateSegment: (id: string, field: "text" | "speakerId", value: string) => void;
  addSpeaker: () => void;
  updateSpeaker: (id: string, patch: Partial<Speaker>) => void;
  removeSpeaker: (id: string) => void;
  setSpeakerVoice: (speakerId: string, voice: string) => void;
  cacheAudio: (id: string, entry: CachedAudio) => void;
  invalidateCache: (id: string) => void;
  clearCache: () => void;
  loadProject: (project: Project, speakers: Speaker[]) => void;
  exportProject: () => Project;
  speakerColor: (speakerId: string) => string;
}

export function useProject(): UseProjectApi {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const addSegment = useCallback(() => {
    dispatch({
      type: "add_segment",
      segment: {
        id: crypto.randomUUID(),
        text: "",
        speakerId: state.speakers[0]?.id ?? null,
      },
    });
  }, [state.speakers]);

  const removeSegment = useCallback((id: string) => {
    dispatch({ type: "remove_segment", id });
  }, []);

  const updateSegment = useCallback(
    (id: string, field: "text" | "speakerId", value: string) => {
      dispatch({ type: "update_segment", id, field, value });
    },
    [],
  );

  const addSpeaker = useCallback(() => {
    const idx = state.speakers.length;
    dispatch({
      type: "add_speaker",
      speaker: {
        id: `speaker-${Date.now()}`,
        name: `Speaker ${idx + 1}`,
        voice: "",
        color: SPEAKER_COLORS[idx % SPEAKER_COLORS.length]!,
      },
    });
  }, [state.speakers.length]);

  const updateSpeaker = useCallback((id: string, patch: Partial<Speaker>) => {
    dispatch({ type: "update_speaker", id, patch });
  }, []);

  const removeSpeaker = useCallback((id: string) => {
    dispatch({ type: "remove_speaker", id });
  }, []);

  const setSpeakerVoice = useCallback((speakerId: string, voice: string) => {
    dispatch({ type: "set_voice", speakerId, voice });
  }, []);

  const cacheAudio = useCallback((id: string, entry: CachedAudio) => {
    dispatch({ type: "cache_audio", id, entry });
  }, []);

  const invalidateCache = useCallback((id: string) => {
    dispatch({ type: "invalidate_cache", id });
  }, []);

  const clearCache = useCallback(() => {
    dispatch({ type: "clear_cache" });
  }, []);

  const loadProject = useCallback((project: Project, speakers: Speaker[]) => {
    // Re-stamp segment ids so two imports don't collide
    const remapped: Segment[] = project.segments.map((s) => ({
      ...s,
      id: crypto.randomUUID(),
    }));
    dispatch({ type: "load_project", project: { ...project, segments: remapped }, speakers });
  }, []);

  const exportProject = useCallback((): Project => {
    return {
      segments: state.segments,
      createdAt: new Date().toISOString(),
      version: "1.0.0",
    };
  }, [state.segments]);

  const speakerColor = useCallback(
    (speakerId: string): string => {
      return state.speakers.find((s) => s.id === speakerId)?.color ?? "#71717a";
    },
    [state.speakers],
  );

  return useMemo(
    () => ({
      segments: state.segments,
      speakers: state.speakers,
      audioCache: state.audioCache,
      addSegment,
      removeSegment,
      updateSegment,
      addSpeaker,
      updateSpeaker,
      removeSpeaker,
      setSpeakerVoice,
      cacheAudio,
      invalidateCache,
      clearCache,
      loadProject,
      exportProject,
      speakerColor,
    }),
    [
      state.segments,
      state.speakers,
      state.audioCache,
      addSegment,
      removeSegment,
      updateSegment,
      addSpeaker,
      updateSpeaker,
      removeSpeaker,
      setSpeakerVoice,
      cacheAudio,
      invalidateCache,
      clearCache,
      loadProject,
      exportProject,
      speakerColor,
    ],
  );
}
