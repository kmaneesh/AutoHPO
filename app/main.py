"""
Composes the FastAPI app: web (static), agent, search, mcp_server. All routes imported here.

Routes:
  GET  /            – Index page (web)
  GET  /health      – Health check (web)
  GET  /static/*    – Static assets
  GET  /api/sse     – SSE for MCP (mcp_server)
  POST /api/chat     – Agent (agent), fallback to search if LLM unavailable
  POST /api/search   – Pure HPO search (search)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import agent, mcp_server, search, web
from app import hpo


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise Meilisearch client, embedder, and agent once at startup."""
    hpo.init_app()
    agent.init_app()
    yield
    # Shutdown: nothing to close (no explicit cleanup required)


app = FastAPI(title="AutoHPO", description="RAG-based HPO term search", lifespan=lifespan)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

web.STATIC_DIR = STATIC_DIR if STATIC_DIR.exists() else None
web.TEMPLATES_DIR = TEMPLATES_DIR if TEMPLATES_DIR.exists() else None

app.include_router(web.router)
app.include_router(agent.router)
app.include_router(search.router)
app.include_router(mcp_server.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
