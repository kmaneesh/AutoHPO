"""
Static pages only: index and health. API routes are defined in agent, search, mcp_server.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

# Set by main when composing the app
STATIC_DIR: Path | None = None
TEMPLATES_DIR: Path | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/")
def index():
    """Serve the main search page from templates first, then static."""
    if TEMPLATES_DIR and (TEMPLATES_DIR / "index.html").exists():
        return FileResponse(TEMPLATES_DIR / "index.html")
    if STATIC_DIR and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {"message": "AutoHPO API. Add app/templates/index.html or app/static/index.html for the UI."}
