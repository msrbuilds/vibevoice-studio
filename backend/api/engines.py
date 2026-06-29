"""GET /api/engines, POST /api/engines/activate — list and switch engines."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.engine_manager import EngineLoadError, EngineManager, EngineNotFound
from ..services.model_download import DOWNLOADABLE as _DOWNLOADABLE
from ..services.model_delete import DELETABLE as _DELETABLE
from .deps import (
    get_engine_installers,
    get_engine_manager,
    get_engine_uninstallers,
    get_model_deleter,
    get_model_downloader,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engines", tags=["engines"])


class EngineLanguageModel(BaseModel):
    code: str
    label: str


class EngineInfoModel(BaseModel):
    name: str
    display_name: str
    description: str
    loaded: bool
    installed: bool
    downloaded: bool
    supports_voice_cloning: bool
    sample_rate: int | None
    max_speakers: int
    default_cfg_scale: float | None
    active: bool
    languages: list[EngineLanguageModel] = []


class EnginesListResponse(BaseModel):
    active: str
    engines: list[EngineInfoModel]


class InstallStatusModel(BaseModel):
    state: str
    log: list[str]
    returncode: int | None


class DownloadStatusModel(BaseModel):
    engine: str | None
    state: str
    percent: float | None
    downloaded_bytes: int
    total_bytes: int | None
    speed_bps: float | None
    eta_sec: float | None
    current_file: str | None
    log: list[str]
    error: str | None
    returncode: int | None


class DeleteWeightsStatusModel(BaseModel):
    state: str  # idle | deleting | deleted | error
    log: list[str]
    error: str | None


class UninstallStatusModel(BaseModel):
    state: str  # idle | uninstalling | uninstalled | error
    log: list[str]
    error: str | None


class ActivateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Engine id to activate")


def _to_model(info: dict) -> EngineInfoModel:
    return EngineInfoModel(
        name=info["name"],
        display_name=info["display_name"],
        description=info["description"],
        loaded=info["loaded"],
        installed=info.get("installed", True),
        downloaded=info.get("downloaded", True),
        supports_voice_cloning=info["supports_voice_cloning"],
        sample_rate=info.get("sample_rate"),
        max_speakers=info["max_speakers"],
        default_cfg_scale=info["default_cfg_scale"],
        active=info.get("active", False),
        languages=[EngineLanguageModel(**lang) for lang in info.get("languages", [])],
    )


@router.get("", response_model=EnginesListResponse)
def list_engines(em: EngineManager = Depends(get_engine_manager)) -> EnginesListResponse:
    """List all available engines and which one is active."""
    return EnginesListResponse(
        active=em.active_name,
        engines=[_to_model(info) for info in em.info()],
    )


@router.post("/activate", response_model=EngineInfoModel)
def activate_engine(
    body: Annotated[ActivateRequest, Body(...)],
    em: EngineManager = Depends(get_engine_manager),
) -> EngineInfoModel:
    """Switch the active TTS engine. Unloads the previous one; the new
    engine is loaded lazily on the next synthesize call.
    """
    try:
        em.activate(body.name)
    except EngineNotFound:
        raise HTTPException(status_code=404, detail=f"unknown engine: {body.name}")

    # Return the now-active engine's info. Don't load it here — the user
    # may want to switch and then run a generation; loading is lazy.
    engine = em.active_engine
    info = {**engine.info(), "name": engine.name, "active": True}
    return _to_model(info)


@router.post("/{name}/load", response_model=EngineInfoModel)
def load_engine(
    name: str,
    em: EngineManager = Depends(get_engine_manager),
) -> EngineInfoModel:
    """Eagerly load an engine (useful for the UI to show a spinner)."""
    try:
        engine = em.get_engine(name)
    except EngineNotFound:
        raise HTTPException(status_code=404, detail=f"unknown engine: {name}")
    try:
        if not engine.is_loaded():
            engine.load()
    except EngineLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Engine load failed")
        raise HTTPException(
            status_code=500, detail=f"engine load failed: {exc}"
        )
    info = {**engine.info(), "name": engine.name, "active": engine.name == em.active_name}
    return _to_model(info)


@router.get("/{name}/install", response_model=InstallStatusModel)
def install_status(name: str, installers=Depends(get_engine_installers)) -> InstallStatusModel:
    """Current install state for an installable engine (Chatterbox / OmniVoice)."""
    inst = installers.get(name)
    if inst is None:
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**inst.status())


@router.post("/{name}/install", response_model=InstallStatusModel)
def start_install(name: str, installers=Depends(get_engine_installers)) -> InstallStatusModel:
    """Start (or coalesce onto a running) install of an isolated engine env."""
    inst = installers.get(name)
    if inst is None:
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**inst.start())


@router.get("/{name}/download", response_model=DownloadStatusModel)
def download_status(name: str, downloader=Depends(get_model_downloader)) -> DownloadStatusModel:
    """Current weight-download state for an in-process engine."""
    if name not in _DOWNLOADABLE:
        raise HTTPException(status_code=400, detail=f"{name} is not downloadable")
    return DownloadStatusModel(**downloader.status())


@router.post("/{name}/download", response_model=DownloadStatusModel)
def start_download(name: str, downloader=Depends(get_model_downloader)) -> DownloadStatusModel:
    """Start (or coalesce onto a running) weight download for the engine."""
    if name not in _DOWNLOADABLE:
        raise HTTPException(status_code=400, detail=f"{name} is not downloadable")
    try:
        return DownloadStatusModel(**downloader.start(name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{name}/delete-weights", response_model=DeleteWeightsStatusModel)
def delete_weights_status(name: str, deleter=Depends(get_model_deleter)) -> DeleteWeightsStatusModel:
    """Current weight-deletion state."""
    if name not in _DELETABLE:
        raise HTTPException(status_code=400, detail=f"{name} weights are not deletable")
    return DeleteWeightsStatusModel(**deleter.status())


@router.post("/{name}/delete-weights", response_model=DeleteWeightsStatusModel)
def start_delete_weights(name: str, deleter=Depends(get_model_deleter)) -> DeleteWeightsStatusModel:
    """Start (or coalesce onto a running) weight deletion."""
    if name not in _DELETABLE:
        raise HTTPException(status_code=400, detail=f"{name} weights are not deletable")
    try:
        return DeleteWeightsStatusModel(**deleter.start(name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{name}/uninstall", response_model=UninstallStatusModel)
def uninstall_status(name: str, uninstallers=Depends(get_engine_uninstallers)) -> UninstallStatusModel:
    """Current env-removal state for an isolated engine (Chatterbox / OmniVoice)."""
    u = uninstallers.get(name)
    if u is None:
        raise HTTPException(status_code=400, detail=f"{name} has no isolated environment to uninstall")
    return UninstallStatusModel(**u.status())


@router.post("/{name}/uninstall", response_model=UninstallStatusModel)
def start_uninstall(name: str, uninstallers=Depends(get_engine_uninstallers)) -> UninstallStatusModel:
    """Start (or coalesce onto a running) removal of an isolated engine env."""
    u = uninstallers.get(name)
    if u is None:
        raise HTTPException(status_code=400, detail=f"{name} has no isolated environment to uninstall")
    return UninstallStatusModel(**u.start())
