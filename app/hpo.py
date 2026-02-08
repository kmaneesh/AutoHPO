"""
Pure Meilisearch HPO search and query normalization. Single place for all queries.
Used by the agent tool and by the search funnel (second layer).
Supports vector (semantic) search when embeddings are available (same model as load_hpo).
No stop-word removal: medical/clinical phrasing is preserved for semantic meaning.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

HPO_INDEX_UID = "hpo"

# Vector search: from env with defaults (must match scripts/load_hpo.py and index settings)
HPO_EMBEDDER_NAME = (os.environ.get("HPO_EMBEDDER_NAME") or "hpo-semantic").strip()
HPO_EMBEDDING_DIMENSIONS = int(os.environ.get("HPO_EMBEDDING_DIMENSIONS", "384"))
HPO_EMBEDDING_MODEL = (os.environ.get("HPO_EMBEDDING_MODEL") or "all-MiniLM-L6-v2").strip()

# Initialised once at app startup (main lifespan)
_client = None
_embedding_model = None


def init_app() -> None:
    """
    Initialise Meilisearch client and embedding model once at app startup.
    Call from FastAPI lifespan so search avoids per-request load time.
    Idempotent: safe to call multiple times.
    """
    global _client, _embedding_model
    if _client is None:
        from meilisearch import Client as MeilisearchClient
        url = (os.environ.get("MEILISEARCH_URL") or "").strip()
        if url:
            api_key = (os.environ.get("MEILI_MASTER_KEY") or "").strip() or None
            _client = MeilisearchClient(url, api_key=api_key)
            logger.info("Meilisearch client initialised: %s", url)
        else:
            logger.warning("MEILISEARCH_URL not set — Meilisearch search will fail")
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer(HPO_EMBEDDING_MODEL)
            logger.info("Embedding model loaded: %s", HPO_EMBEDDING_MODEL)
        except ImportError:
            logger.warning("sentence-transformers not installed — vector search disabled")


def _get_embedding_model():
    """Return the app-initialised embedding model, or None if not installed."""
    return _embedding_model


def _embed_query(text: str) -> list[float] | None:
    """Embed the query string with the HPO model. Returns None if model unavailable."""
    if not (text or "").strip():
        return None
    model = _get_embedding_model()
    if model is None:
        return None
    vec = model.encode(text.strip(), convert_to_numpy=True)
    return vec.tolist()

def prepare_search_query(query: str) -> str:
    """
    Prepare a query for HPO search: normalize whitespace only.
    No stop-word removal so medical/clinical semantic meaning is preserved.
    Single entry point; used inside search_hpo so all callers get the same behaviour.
    """
    if not (query or "").strip():
        return ""
    return " ".join(query.strip().split())


def get_client():
    """Return the Meilisearch client (initialised at app startup or on first use)."""
    global _client
    if _client is None:
        init_app()
    if _client is None:
        raise ValueError("MEILISEARCH_URL is not set")
    return _client


def search_hpo(query: str, limit: int = 10) -> str:
    """
    Search the Human Phenotype Ontology (HPO) index via Meilisearch.
    Query is normalized (whitespace only) before search; no stop-word removal.
    When embeddings are available, uses hybrid search (full-text + vector).
    No agent, no fallbacks.

    Args:
        query: Search query (e.g. "atrial septal defect", "HP:0001631").
        limit: Maximum number of HPO terms to return (default 10).

    Returns:
        JSON string of list of dicts with hpo_id, name, definition, synonyms_str.
    """
    q = prepare_search_query(query)
    search_q = q if q else query.strip()
    client = get_client()
    index = client.index(HPO_INDEX_UID)

    search_params: dict = {"limit": limit}
    query_vector = _embed_query(search_q) if search_q else None
    if query_vector is not None:
        search_params["vector"] = query_vector
        search_params["hybrid"] = {"embedder": HPO_EMBEDDER_NAME}

    response = index.search(search_q, search_params)
    hits = response.get("hits") or []
    out = [
        {
            "hpo_id": h.get("hpo_id"),
            "name": h.get("name"),
            "definition": (h.get("definition") or "")[:500],
            "synonyms_str": h.get("synonyms_str") or "",
        }
        for h in hits
    ]
    return json.dumps(out, indent=2)


def search_hpo_results(query: str, limit: int = 5) -> tuple[list[dict], dict]:
    """
    Hybrid search (full-text + vector) over HPO index; returns (results, debug_info).
    debug_info contains query_sent, search_params, hit_count, raw_keys, and any error.
    """
    debug: dict = {"query_raw": query, "query_sent": "", "search_params": {}, "hit_count": 0, "raw_first_hit_keys": [], "error": None}
    q = prepare_search_query(query)
    search_q = q if q else query.strip()
    debug["query_sent"] = search_q
    if not search_q:
        debug["error"] = "empty query after normalization"
        return [], debug
    try:
        client = get_client()
        index = client.index(HPO_INDEX_UID)
        search_params: dict = {"limit": limit}
        query_vector = _embed_query(search_q)
        if query_vector is not None:
            search_params["vector"] = f"[{len(query_vector)} dims]"
            search_params["hybrid"] = {"embedder": HPO_EMBEDDER_NAME}
            # actual params for the call (vector is full list)
            actual_params: dict = {"limit": limit, "vector": query_vector, "hybrid": {"embedder": HPO_EMBEDDER_NAME}}
        else:
            actual_params = search_params
            debug["vector"] = "no embedding model"
        debug["search_params"] = search_params
        response = index.search(search_q, actual_params)
        hits = response.get("hits") or []
        debug["hit_count"] = len(hits)
        if hits:
            debug["raw_first_hit_keys"] = list(hits[0].keys())
        logger.info("search_hpo_results(%r) → %d hits", search_q, len(hits))
        results = [
            {
                "hpo_id": h.get("hpo_id"),
                "name": h.get("name"),
                "definition": (h.get("definition") or "")[:500],
                "synonyms_str": h.get("synonyms_str") or "",
            }
            for h in hits
        ]
        return results, debug
    except Exception as exc:
        logger.error("search_hpo_results(%r) FAILED: %s", search_q, exc, exc_info=True)
        debug["error"] = str(exc)
        return [], debug


def get_term_by_id(term_id: str) -> dict | None:
    """
    Fetch a single HPO term by ID (e.g. HP:0001631 or HP_0001631).
    Returns dict with hpo_id, name, definition, synonyms_str or None if not found.
    """
    if not (term_id or "").strip():
        return None
    q = term_id.strip().replace("_", ":", 1) if "_" in term_id else term_id.strip()
    try:
        client = get_client()
        index = client.index(HPO_INDEX_UID)
        doc = index.get_document(q)
        if not doc:
            return None
        return {
            "hpo_id": doc.get("hpo_id"),
            "name": doc.get("name"),
            "definition": (doc.get("definition") or "")[:500],
            "synonyms_str": doc.get("synonyms_str") or "",
        }
    except Exception:
        return None
