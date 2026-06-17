"""Voice management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from ..core.exceptions import BuiltInVoiceProtected, VoiceInvalid, VoiceNotFound
from ..services.voices import VoiceInfo, VoiceRegistry
from .deps import get_voice_registry
from .schemas import UploadVoiceResponse, VoiceInfoModel, VoiceListResponse, VoiceMetaUpdate

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("", response_model=VoiceListResponse)
def list_voices(reg: VoiceRegistry = Depends(get_voice_registry)) -> VoiceListResponse:
    items = [
        VoiceInfoModel(
            id=v.id,
            name=v.name,
            gender=v.gender,
            language=v.language,
            source=v.source,
            size_bytes=v.size_bytes,
            duration_sec=v.duration_sec,
            sample_rate=v.sample_rate,
        )
        for v in reg.list()
    ]
    return VoiceListResponse(voices=items)


@router.post(
    "/upload",
    response_model=UploadVoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_voice(
    file: UploadFile = File(...),
    name: str | None = Form(default=None, description="Display name (e.g. 'Amelia')"),
    gender: str | None = Form(default=None, description="'man', 'woman', or 'nonbinary'"),
    language: str | None = Form(default=None, description="Language tag, e.g. 'en'"),
    reg: VoiceRegistry = Depends(get_voice_registry),
) -> UploadVoiceResponse:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        info = reg.save_upload(
            raw,
            file.filename or "voice.wav",
            name=name,
            gender=gender,
            language=language,
        )
    except VoiceInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return UploadVoiceResponse(
        id=info.id,
        name=info.name,
        size_bytes=info.size_bytes or 0,
        duration_sec=info.duration_sec or 0.0,
        sample_rate=info.sample_rate or 0,
    )


@router.post("/{voice_id}/meta", response_model=VoiceInfoModel)
def update_voice_meta(
    voice_id: str,
    body: VoiceMetaUpdate,
    reg: VoiceRegistry = Depends(get_voice_registry),
) -> VoiceInfoModel:
    """Update name / gender / language for an existing voice (built-in or upload)."""
    try:
        info = reg.update_meta(
            voice_id,
            name=body.name,
            gender=body.gender,
            language=body.language,
        )
    except BuiltInVoiceProtected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except VoiceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoiceInfoModel(
        id=info.id,
        name=info.name,
        gender=info.gender,
        language=info.language,
        source=info.source,
        size_bytes=info.size_bytes,
        duration_sec=info.duration_sec,
        sample_rate=info.sample_rate,
    )


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice(voice_id: str, reg: VoiceRegistry = Depends(get_voice_registry)) -> JSONResponse:
    try:
        reg.delete(voice_id)
    except BuiltInVoiceProtected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except VoiceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(status_code=204, content=None)
