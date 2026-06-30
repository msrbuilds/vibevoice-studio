"""GET/POST /api/update — version check + one-click apply."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_update_checker, get_update_runner

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateInfoModel(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    html_url: str | None = None
    published_at: str | None = None
    body: str | None = None
    checked_at: float = 0.0
    error: str | None = None


class UpdateRunStatusModel(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    log: list[str]
    returncode: int | None = None
    error: str | None = None


@router.get("", response_model=UpdateInfoModel)
def update_info(force: bool = False, checker=Depends(get_update_checker)) -> UpdateInfoModel:
    """Latest-release comparison. `?force=1` bypasses the cache."""
    return UpdateInfoModel(**checker.check(force=force))


@router.post("", response_model=UpdateRunStatusModel)
def start_update(checker=Depends(get_update_checker), runner=Depends(get_update_runner)) -> UpdateRunStatusModel:
    """Start (or coalesce onto a running) update to the latest release tag."""
    snap = checker.check()
    if not snap.get("update_available") or not snap.get("latest"):
        raise HTTPException(status_code=400, detail="no update available")
    # studio.py expects the tag form (v-prefixed); the snapshot stores it bare.
    tag = f"v{snap['latest']}"
    return UpdateRunStatusModel(**runner.start(tag))


@router.get("/run", response_model=UpdateRunStatusModel)
def update_run_status(runner=Depends(get_update_runner)) -> UpdateRunStatusModel:
    """Live status + log of the in-progress (or last) update run."""
    return UpdateRunStatusModel(**runner.status())
