"""
Composes the FastAPI app: web (static), agent, search, mcp_server. All routes imported here.

Routes:
  GET  /            – Index page (web)
  GET  /health      – Health check (web)
  GET  /static/*    – Static assets
  GET  /api/sse     – SSE for MCP (mcp_server)
  POST /api/chat     – Agent (extract terms from history)
  POST /api/search   – Pure HPO search (in-memory regex)
  POST /api/vector   – Pure vector search (semantic similarity only)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import agent, hpo, mcp_server, search, web


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise once at startup: HPO loader (search), Meilisearch client (hpo), agent singleton. All inits are idempotent."""
    search.init_app()   # Load data/hp.json once for in-memory regex search
    hpo.init_app()     # Meilisearch client + embedding model once
    agent.init_app()   # Agent singleton (history, tools) once
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
