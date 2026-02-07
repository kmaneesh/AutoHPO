"""
Search funnel and POST /api/search endpoint.
Funnel: Meilisearch (hpo) then regex on data/hp.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.hpo import prepare_search_query, search_hpo

router = APIRouter()


class SearchRequest(BaseModel):
    query: str


@router.post("/api/search")
def api_search(body: SearchRequest):
    """Pure HPO search: Meilisearch then regex on hp.json. Returns query_sent (after normalization) and results."""
    try:
        query_sent = prepare_search_query(body.query)
        results = search_funnel(query=body.query, limit=15)
        return {"query_sent": query_sent, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Project root and data path (hp.json)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_HP_JSON_PATH = _PROJECT_ROOT / "data" / "hp.json"


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


def regex_search_hp_json(query: str, limit: int = 10) -> list[dict]:
    """
    Fallback: search data/hp.json with a simple regex/substring match on
    hpo_id, name, definition, synonyms_str. Returns same shape as Meilisearch.
    """
    if not _HP_JSON_PATH.exists():
        return []
    terms = _parse_obographs(_HP_JSON_PATH)
    q = (query or "").strip().lower()
    if not q:
        return terms[:limit]
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    matched = []
    for t in terms:
        if (
            pattern.search(t.get("hpo_id") or "")
            or pattern.search(t.get("name") or "")
            or pattern.search(t.get("definition") or "")
            or pattern.search(t.get("synonyms_str") or "")
        ):
            matched.append(t)
            if len(matched) >= limit:
                break
    return matched


def search_funnel(query: str, limit: int = 15) -> list[dict]:
    """
    Funnel: (1) Meilisearch via hpo.search_hpo (normalizes query internally); (2) on failure, regex on data/hp.json.
    Returns list of dicts with hpo_id, name, definition, synonyms_str.
    """
    try:
        raw = search_hpo(query=query, limit=limit)
        return json.loads(raw)
    except Exception:
        pass
    q = prepare_search_query(query)
    return regex_search_hp_json(query=q, limit=limit)
