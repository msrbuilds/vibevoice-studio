"""Domain exceptions for the backend.

These are caught by global handlers in `app.py` and mapped to HTTP responses.
"""

from __future__ import annotations


class BackendError(Exception):
    """Base class for all domain errors."""

    code: str = "backend_error"
    http_status: int = 500

    def __init__(self, message: str, *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class VoiceNotFound(BackendError):
    code = "voice_not_found"
    http_status = 404


class VoiceInvalid(BackendError):
    code = "voice_invalid"
    http_status = 400


class BuiltInVoiceProtected(BackendError):
    code = "builtin_voice_protected"
    http_status = 403


class TextInvalid(BackendError):
    code = "text_invalid"
    http_status = 400


class ModelNotLoaded(BackendError):
    code = "model_not_loaded"
    http_status = 503


class OutOfMemory(BackendError):
    code = "out_of_memory"
    http_status = 507


class SynthesisTimeout(BackendError):
    code = "synthesis_timeout"
    http_status = 504
