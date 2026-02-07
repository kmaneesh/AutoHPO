"""
FastAPI app for AutoHPO. Serves static frontend, health, agent chat, and fallback search.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="AutoHPO", description="RAG-based HPO term search")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    """Serve the main search page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AutoHPO API. Add static/index.html for the UI."}


@app.post("/api/chat", response_model=ChatResponse)
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


@app.post("/api/search/fallback")
def api_search_fallback(body: ChatRequest):
    """Direct Meilisearch search when the agent is unavailable. Returns JSON list of HPO terms."""
    try:
        from app.search import search_hpo
        raw = search_hpo(body.query, limit=15)
        return {"results": json.loads(raw)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
