"""
All FastAPI routes: health, index, api/chat, api/search/fallback.
Static and templates are mounted in main.py from app/static and app/templates.
One job: HTTP routes only; delegates to agent and search funnel.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

# Paths relative to app/ (set by main when mounting)
STATIC_DIR: Path | None = None
TEMPLATES_DIR: Path | None = None


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/")
def index():
    """Serve the main search page from static or templates."""
    if STATIC_DIR and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    if TEMPLATES_DIR and (TEMPLATES_DIR / "index.html").exists():
        return FileResponse(TEMPLATES_DIR / "index.html")
    return {"message": "AutoHPO API. Add app/static/index.html or app/templates/index.html for the UI."}


@router.post("/api/chat", response_model=ChatResponse)
def api_chat(body: ChatRequest):
    """Run the HPO agent on a natural language query. Requires OPENAI_API_KEY."""
    try:
        from app.agent import get_agent
        agent = get_agent()
        run = agent.run(body.query)
        content = getattr(run, "content", None) or str(run)
        return ChatResponse(response=content or "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/search/fallback")
def api_search_fallback(body: ChatRequest):
    """Search funnel: Meilisearch then regex on hp.json. Returns JSON list of HPO terms."""
    try:
        from app.search import search_funnel
        results = search_funnel(query=body.query, limit=15)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
