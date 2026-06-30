"""VoiceRegistry: scans built-in voices directory and manages user uploads."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from ..core.exceptions import BuiltInVoiceProtected, VoiceInvalid, VoiceNotFound

log = logging.getLogger(__name__)

# Optional per-directory metadata. If `voices/voices.json` exists, it's merged
# on top of the auto-derived voice info. Keys are voice ids (filename stems).
_VOICE_META_FILENAME = "voices.json"
_VALID_GENDERS = {"man", "woman", "male", "female", "nonbinary"}

# Allowed audio formats for uploads. WAV is always allowed; others depend on libsndfile.
ALLOWED_UPLOAD_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3"}

# Validation bounds
MIN_DURATION_S = 1.0
MAX_DURATION_S = 60.0
MIN_SR = 8_000
MAX_SR = 48_000

# Filename stem pattern: keep alnum, dash, underscore. Anything else becomes "_".
_SAFE_STEM = re.compile(r"[^A-Za-z0-9_-]+")

# How much of a WAV header we trust to detect the format
_MAX_PROBE_BYTES = 256 * 1024  # 256 KiB is plenty to read a header


@dataclass
class VoiceInfo:
    id: str
    name: str
    gender: str | None
    language: str | None
    source: str  # "builtin" or "upload"
    size_bytes: int | None = None
    duration_sec: float | None = None
    sample_rate: int | None = None
    # Which TTS engine owns this voice ("vibevoice", "kokoro", ...). For
    # filesystem-based voices, this is set at registration time.
    engine: str | None = None
    # Optional transcript of the reference clip, used by VoxCPM "ultimate
    # cloning". None when unset. Persisted in voices.json.
    reference_transcript: str | None = None


@dataclass
class _VoiceEntry:
    info: VoiceInfo
    path: Path
    is_builtin: bool


class VoiceRegistry:
    """Single source of truth for available voices.

    Built-in voices are read-only and discovered from `voices_dir`.
    User-uploaded voices live in `uploads_dir` and are mutable.
    """

    def __init__(self, voices_dir: Path, uploads_dir: Path) -> None:
        self.voices_dir = Path(voices_dir)
        self.uploads_dir = Path(uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache of voice metadata for both built-in and uploads.
        # Loaded from voices.json (built-in) and uploads/voices.json (uploads)
        # on construction. Modified by save_upload() and update_meta().
        self._meta: dict[str, dict] = {}
        self._meta_sources: dict[str, Path] = {}  # voice_id -> which json file owns it
        # Per-engine voice registries. Engines that have their own
        # built-in voice catalog (Kokoro) call `register_engine_voices()`
        # to inject their voices into the global listing. The voice ids
        # are namespaced with the engine name in the dict to avoid
        # collisions if two engines happen to use the same id.
        self._engine_voices: dict[str, list[VoiceInfo]] = {}
        self._load_meta()

    # ------------------------------------------------------------------ scan --

    def _scan_builtin(self) -> list[_VoiceEntry]:
        if not self.voices_dir.exists():
            return []
        # Accept wav/mp3/flac/ogg as built-in reference audio. The processor
        # only consumes audio bytes; the file extension doesn't matter to it.
        meta_overrides = self._load_meta_overrides()
        entries: list[_VoiceEntry] = []
        for ext in ("*.wav", "*.mp3", "*.flac", "*.ogg"):
            for path in sorted(self.voices_dir.glob(ext)):
                if not path.is_file():
                    continue
                stem = path.stem
                override = meta_overrides.get(stem, {})
                entries.append(
                    _VoiceEntry(
                        info=VoiceInfo(
                            id=stem,
                            name=override.get("name") or self._display_name(stem),
                            gender=override.get("gender") or self._guess_gender(stem),
                            language=override.get("language") or self._guess_lang(stem),
                            source="builtin",
                            size_bytes=path.stat().st_size,
                            reference_transcript=override.get("reference_transcript"),
                        ),
                        path=path.resolve(),
                        is_builtin=True,
                    )
                )
        return entries

    def _load_meta_overrides(self) -> dict[str, dict]:
        """Load voices.json from the built-in directory, if present.

        Format: { "filename_stem": {"name": "...", "gender": "man|woman|...",
        "language": "en|es|...", "reference_transcript": "..."} }
        """
        path = self.voices_dir / _VOICE_META_FILENAME
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Invalid %s: %s", _VOICE_META_FILENAME, exc)
            return {}
        if not isinstance(data, dict):
            log.warning("%s must be a JSON object at the top level", _VOICE_META_FILENAME)
            return {}
        result: dict[str, dict] = {}
        for voice_id, meta in data.items():
            if not isinstance(meta, dict):
                continue
            clean: dict = {}
            if "name" in meta and isinstance(meta["name"], str):
                clean["name"] = meta["name"].strip()
            if "gender" in meta and isinstance(meta["gender"], str):
                g = meta["gender"].strip().lower()
                if g in _VALID_GENDERS:
                    clean["gender"] = "man" if g in ("man", "male") else (
                        "woman" if g in ("woman", "female") else "nonbinary"
                    )
            if "language" in meta and isinstance(meta["language"], str):
                clean["language"] = meta["language"].strip().lower()[:8]
            if "reference_transcript" in meta and isinstance(meta["reference_transcript"], str):
                clean["reference_transcript"] = meta["reference_transcript"].strip()
            result[str(voice_id)] = clean
        return result

    def _scan_uploads(self) -> list[_VoiceEntry]:
        entries: list[_VoiceEntry] = []
        # Also pick up any WAV/MP3/FLAC/OGG in uploads/, not just user-* prefixed
        for ext in ("*.wav", "*.mp3", "*.flac", "*.ogg"):
            for wav in sorted(self.uploads_dir.glob(ext)):
                if not wav.is_file():
                    continue
                if wav.name.startswith(".") or wav.name == _VOICE_META_FILENAME:
                    continue
                stem = wav.stem
                # Best-effort metadata (file might be corrupt; skip gracefully)
                size = wav.stat().st_size
                duration: float | None = None
                sr: int | None = None
                try:
                    info = sf.info(str(wav))
                    duration = float(info.frames) / float(info.samplerate)
                    sr = int(info.samplerate)
                except Exception:  # noqa: BLE001
                    pass
                override = self._meta.get(stem, {})
                entries.append(
                    _VoiceEntry(
                        info=VoiceInfo(
                            id=stem,
                            name=override.get("name") or self._display_name(stem),
                            gender=override.get("gender"),
                            language=override.get("language"),
                            source="upload",
                            size_bytes=size,
                            duration_sec=duration,
                            sample_rate=sr,
                            reference_transcript=override.get("reference_transcript"),
                        ),
                        path=wav.resolve(),
                        is_builtin=False,
                    )
                )
        return entries

    # ---- metadata persistence ----

    def _load_meta(self) -> None:
        """Load metadata from both built-in and uploads voices.json files."""
        for path in (self.voices_dir / _VOICE_META_FILENAME,
                     self.uploads_dir / _VOICE_META_FILENAME):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("Invalid %s: %s", path, exc)
                continue
            if not isinstance(data, dict):
                continue
            for voice_id, meta in data.items():
                if isinstance(meta, dict):
                    self._meta[str(voice_id)] = meta
                    self._meta_sources[str(voice_id)] = path

    def _save_meta(self, voice_id: str) -> None:
        """Write the meta entry for one voice to its owning voices.json file."""
        path = self._meta_sources.get(voice_id)
        if path is None:
            return
        try:
            existing: dict = {}
            if path.is_file():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8")) or {}
                except Exception:  # noqa: BLE001
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing[voice_id] = self._meta[voice_id]
            path.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to save %s: %s", path, exc)

    def update_meta(
        self,
        voice_id: str,
        name: str | None = None,
        gender: str | None = None,
        language: str | None = None,
        reference_transcript: str | None = None,
    ) -> VoiceInfo:
        """Update name / gender / language / reference_transcript for any voice (built-in or upload).

        Built-in voices: the owning file is `voices/voices.json`. The WAV
        itself is not moved.
        Upload voices: the owning file is `uploads/voices.json`.
        """
        if self.is_builtin(voice_id):
            source_path = self.voices_dir / _VOICE_META_FILENAME
        elif (self.uploads_dir / f"{voice_id}.wav").is_file() or any(
            (self.uploads_dir / f"{voice_id}{ext}").is_file()
            for ext in (".wav", ".mp3", ".flac", ".ogg")
        ):
            source_path = self.uploads_dir / _VOICE_META_FILENAME
        else:
            raise VoiceNotFound(f"voice not found: {voice_id}")

        current = self._meta.get(voice_id, {})
        if name is not None:
            current["name"] = name.strip()
        if gender is not None:
            g = gender.strip().lower()
            if g in _VALID_GENDERS:
                current["gender"] = "man" if g in ("man", "male") else (
                    "woman" if g in ("woman", "female") else "nonbinary"
                )
            elif gender == "" or gender.lower() == "none":
                current["gender"] = None
        if language is not None:
            current["language"] = language.strip().lower()[:8] if language else None
        if reference_transcript is not None:
            rt = reference_transcript.strip()
            current["reference_transcript"] = rt or None

        self._meta[voice_id] = current
        self._meta_sources[voice_id] = source_path
        self._save_meta(voice_id)

        # Return the fresh info
        all_voices = {e.info.id: e.info for e in self._scan_builtin() + self._scan_uploads()}
        if voice_id not in all_voices:
            raise VoiceNotFound(f"voice not found: {voice_id}")
        return all_voices[voice_id]

    # ------------------------------------------------------------------- API --

    def list(self) -> list[VoiceInfo]:
        """Return the merged voice catalog: filesystem voices + engine voices.

        Filesystem voices (built-in directory + user uploads) are tagged
        with engine="vibevoice" since that's the only engine that supports
        voice cloning from arbitrary audio. Engine voices come from the
        per-engine registries populated via `register_engine_voices()`.
        """
        fs_voices: list[VoiceInfo] = []
        for e in self._scan_builtin() + self._scan_uploads():
            # Filesystem voices only work with voice-cloning engines. We
            # default the tag to "vibevoice"; an engine that explicitly
            # wants filesystem voices would be set up to claim them.
            e.info.engine = e.info.engine or "vibevoice"
            fs_voices.append(e.info)
        engine_voices: list[VoiceInfo] = []
        for engine_name, voices in self._engine_voices.items():
            for v in voices:
                v.engine = engine_name
                engine_voices.append(v)
        return fs_voices + engine_voices

    def register_engine_voices(self, engine_name: str, voices: list[VoiceInfo]) -> None:
        """Add (or replace) the voice catalog for an engine.

        Called at app startup by `EngineManager` for every engine that
        exposes a built-in voice set. VibeVoice uses an empty list (its
        voices come from the filesystem).
        """
        self._engine_voices[engine_name] = list(voices)

    def get_engine_for_voice(self, voice_id: str) -> str | None:
        """Which engine owns this voice id? Returns None if not found."""
        for v in self.list():
            if v.id == voice_id:
                return v.engine
        return None

    def get(self, voice_id: str) -> Path:
        if not voice_id:
            raise VoiceNotFound("empty voice id")
        # Search by filename stem across all supported audio formats.
        # Built-in first, then uploads.
        for ext in (".wav", ".mp3", ".flac", ".ogg"):
            for base in (self.voices_dir, self.uploads_dir):
                path = base / f"{voice_id}{ext}"
                if path.is_file():
                    return path.resolve()
        raise VoiceNotFound(f"voice not found: {voice_id}")

    def is_builtin(self, voice_id: str) -> bool:
        return (self.voices_dir / f"{voice_id}.wav").is_file()

    def get_language(self, voice_id: str) -> str | None:
        """Return the language code for a voice (e.g. 'ur', 'en'), or None.

        Used by the synthesizer to inject a language hint into the model
        prompt when generating non-English speech.
        """
        for v in self.list():
            if v.id == voice_id:
                return v.language
        return None

    def get_reference_transcript(self, voice_id: str) -> str | None:
        """Return the stored reference transcript for a voice, or None.

        Used by VoxCPM "ultimate cloning" to pass a prompt transcript that
        guides high-fidelity continuation from the reference clip.
        """
        for v in self.list():
            if v.id == voice_id:
                return v.reference_transcript
        return None

    def save_upload(
        self,
        file_bytes: bytes,
        original_filename: str,
        name: str | None = None,
        gender: str | None = None,
        language: str | None = None,
    ) -> VoiceInfo:
        """Validate and persist a user-uploaded voice. Returns the new voice's info."""
        suffix = Path(original_filename).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise VoiceInvalid(
                f"unsupported format {suffix!r}; allowed: {sorted(ALLOWED_UPLOAD_SUFFIXES)}"
            )

        # Probe with soundfile first to catch garbage early
        try:
            with sf.SoundFile(io.BytesIO(file_bytes)) as f:
                sr = f.samplerate
                frames = f.frames
                channels = f.channels
        except Exception as exc:  # noqa: BLE001
            raise VoiceInvalid(f"could not decode audio: {exc}") from exc

        if not (MIN_SR <= sr <= MAX_SR):
            raise VoiceInvalid(f"sample rate {sr} out of range [{MIN_SR}, {MAX_SR}]")
        duration = frames / float(sr)
        if not (MIN_DURATION_S <= duration <= MAX_DURATION_S):
            raise VoiceInvalid(
                f"duration {duration:.2f}s out of range [{MIN_DURATION_S}, {MAX_DURATION_S}]"
            )

        # Sanitize the stem
        base_stem = Path(original_filename).stem
        safe = _SAFE_STEM.sub("_", base_stem).strip("_") or "voice"
        # Add a short hash to avoid collisions; 6 hex chars
        digest = hashlib.sha1(file_bytes).hexdigest()[:6]
        # If user provided a name, prefer it (but still add the hash for uniqueness)
        target_id = f"user-{safe}-{digest}"
        target_path = self.uploads_dir / f"{target_id}.wav"

        # Always write as canonical 16-bit PCM WAV (soundfile default with subtype='PCM_16')
        with sf.SoundFile(
            str(target_path),
            mode="w",
            samplerate=sr,
            channels=min(channels, 2),  # the 1.5B only consumes mono
            subtype="PCM_16",
        ) as out:
            with sf.SoundFile(io.BytesIO(file_bytes)) as inp:
                out.write(inp.read(dtype="int16"))

        # Persist metadata (name / gender / language) if provided
        meta: dict = {}
        if name is not None and name.strip():
            meta["name"] = name.strip()
        if gender is not None and gender.strip():
            g = gender.strip().lower()
            if g in _VALID_GENDERS:
                meta["gender"] = "man" if g in ("man", "male") else (
                    "woman" if g in ("woman", "female") else "nonbinary"
                )
        if language is not None and language.strip():
            meta["language"] = language.strip().lower()[:8]
        if meta:
            self._meta[target_id] = meta
            self._meta_sources[target_id] = self.uploads_dir / _VOICE_META_FILENAME
            self._save_meta(target_id)

        log.info("Saved uploaded voice %s (sr=%d, duration=%.2fs)", target_id, sr, duration)
        return VoiceInfo(
            id=target_id,
            name=meta.get("name") or safe,
            gender=meta.get("gender"),
            language=meta.get("language"),
            source="upload",
            size_bytes=target_path.stat().st_size,
            duration_sec=duration,
            sample_rate=sr,
        )

    def delete(self, voice_id: str) -> None:
        if not voice_id:
            raise VoiceNotFound("empty voice id")
        if self.is_builtin(voice_id):
            raise BuiltInVoiceProtected(f"cannot delete built-in voice: {voice_id}")
        target = self.uploads_dir / f"{voice_id}.wav"
        if not target.is_file():
            raise VoiceNotFound(f"voice not found: {voice_id}")
        target.unlink()
        log.info("Deleted uploaded voice %s", voice_id)

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _display_name(stem: str) -> str:
        """en-Emma_woman -> Emma (woman)"""
        parts = stem.split("-", 1)
        name_part = parts[1] if len(parts) == 2 else parts[0]
        # Replace _ with space
        return name_part.replace("_", " ").strip() or stem

    @staticmethod
    def _guess_gender(stem: str) -> str | None:
        low = stem.lower()
        if "woman" in low or "female" in low:
            return "woman"
        if "man" in low or "male" in low:
            return "man"
        return None

    @staticmethod
    def _guess_lang(stem: str) -> str | None:
        # Filenames we ship start with "en-" or similar
        if "-" in stem:
            return stem.split("-", 1)[0]
        return None


# Convenience export so the random-token name doesn't sit unused
_ = secrets
