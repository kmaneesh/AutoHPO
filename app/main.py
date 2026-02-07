"""
Composes the FastAPI app: web routes, static (app/static), templates (app/templates).
Maps endpoints: /, /health, /api/chat, /api/search/fallback.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import web

app = FastAPI(title="AutoHPO", description="RAG-based HPO term search")

# Static and templates inside app/
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

web.STATIC_DIR = STATIC_DIR if STATIC_DIR.exists() else None
web.TEMPLATES_DIR = TEMPLATES_DIR if TEMPLATES_DIR.exists() else None

app.include_router(web.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
