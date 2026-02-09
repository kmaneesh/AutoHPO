"""
Pure regex search over in-memory HPO data (loaded once at startup).
POST /api/search: keyword/typeahead style. No Meilisearch at runtime.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


_ROOT = Path(__file__).resolve().parent.parent
_HP_JSON_PATH = _ROOT / "data" / "hp.json"

# Loaded once at startup
_terms: list[dict] = []


def _normalize_query(query: str) -> str:
    """Normalize query for search: empty if blank, else single-space-joined words."""
    if not (query or "").strip():
        return ""
    return " ".join(query.strip().split())


def _curie_from_id(node_id: str) -> str:
    """Convert OBO IRI to CURIE (e.g. http://.../HP_0000123 -> HP:0000123)."""
    if not node_id:
        return ""
    if "://" in node_id:
        part = node_id.split("/")[-1]
        if "_" in part:
            ns, rest = part.split("_", 1)
            return f"{ns.upper()}:{rest}"
        return part
    return node_id.replace("_", ":", 1) if "_" in node_id else node_id


def _parse_obographs(path: Path) -> list[dict]:
    """Parse obographs JSON to list of dicts with hpo_id, name, definition, synonyms_str."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for graph in data.get("graphs", []):
        for node in graph.get("nodes", []):
            node_id = node.get("id") or ""
            curie = _curie_from_id(node_id)
            name = (node.get("lbl") or "").strip()
            meta = node.get("meta") or {}
            defn = ""
            if isinstance(meta.get("definition"), dict):
                defn = (meta["definition"].get("val") or "").strip()
            synonyms = []
            for s in meta.get("synonyms", []):
                if isinstance(s, dict) and s.get("val"):
                    synonyms.append(str(s["val"]).strip())
            synonyms_str = " | ".join(synonyms) if synonyms else ""
            out.append({
                "hpo_id": curie,
                "name": name,
                "definition": defn,
                "synonyms_str": synonyms_str,
            })
    return out


def init_app() -> None:
    """Load data/hp.json once at startup. Idempotent."""
    global _terms
    if _terms:
        return
    if not _HP_JSON_PATH.exists():
        return
    _terms[:] = _parse_obographs(_HP_JSON_PATH)


def get_terms() -> list[dict]:
    """Return the in-memory HPO terms (empty if not loaded)."""
    return _terms


def search(query: str, limit: int = 15) -> list[dict]:
    """
    Regex search over in-memory terms (hpo_id, name, definition, synonyms_str).
    Returns list of dicts with hpo_id, name, definition, synonyms_str.
    Empty query returns first `limit` terms (for typeahead/select2).
    """
    init_app()
    if not _terms:
        return []
    q = (query or "").strip()
    if not q:
        return _terms[:limit]
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    matched = []
    for t in _terms:
        if (
            pattern.search(t.get("hpo_id") or "")
            or pattern.search(t.get("name") or "")
            or pattern.search(t.get("definition") or "")
            or pattern.search(t.get("synonyms_str") or "")
        ):
            matched.append({
                "hpo_id": t.get("hpo_id"),
                "name": t.get("name"),
                "definition": (t.get("definition") or "")[:500],
                "synonyms_str": t.get("synonyms_str") or "",
            })
            if len(matched) >= limit:
                break
    return matched


def get_term_by_id(term_id: str) -> dict | None:
    """Return a single term by HPO ID (e.g. HP:0001631 or HP_0001631)."""
    init_app()
    if not _terms:
        return None
    q = term_id.strip().replace("_", ":", 1) if "_" in term_id else term_id.strip()
    for t in _terms:
        if (t.get("hpo_id") or "").upper() == q.upper():
            return {
                "hpo_id": t.get("hpo_id"),
                "name": t.get("name"),
                "definition": (t.get("definition") or "")[:500],
                "synonyms_str": t.get("synonyms_str") or "",
            }
    return None


# --- API ---

class SearchRequest(BaseModel):
    query: str


@router.post("/api/search")
def api_search(body: SearchRequest):
    """Pure HPO search: regex over in-memory hp.json. Returns query_sent (normalized) and results."""
    try:
        query_sent = _normalize_query(body.query)
        results = search(query=query_sent or body.query.strip(), limit=15)
        return {"query_sent": query_sent, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/vector")
def api_vector_search(body: SearchRequest):
    """Pure vector search: semantic similarity only (no keyword matching). Returns results from Meilisearch embeddings."""
    try:
        from app import hpo
        results, debug = hpo.vector_search_hpo(body.query, limit=15)
        return {
            "query_sent": debug.get("query_sent", ""),
            "results": results,
            "debug": debug if _debug_enabled() else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _debug_enabled() -> bool:
    """Check if debug mode is enabled via environment variable."""
    import os
    return os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")
