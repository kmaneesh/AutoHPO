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
HPO_EMBEDDING_DIMENSIONS = int(os.environ.get("HPO_EMBEDDING_DIMENSIONS", "384"))
HPO_EMBEDDING_MODEL = (os.environ.get("HPO_EMBEDDING_MODEL") or "all-MiniLM-L6-v2").strip()

# Initialised once at app startup (main lifespan)
_client = None
_index = None  # cached Index object (avoids recreating per call)
_embedding_model = None


def _configure_session(client) -> None:
    """Mount retry + connection-pool adapter on the client's requests.Session."""
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=4,
            pool_maxsize=10,
        )
        # The meilisearch SDK stores the session at client.http.session (HttpRequests)
        session = client.http.session
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logger.info("Meilisearch session configured: retry=3, pool_connections=4, pool_maxsize=10")
    except Exception as exc:
        logger.warning("Could not configure Meilisearch session adapter: %s", exc)


def init_app() -> None:
    """
    Initialise Meilisearch client (with persistent session + retry), cached index,
    and embedding model once at app startup. Idempotent.
    """
    global _client, _index, _embedding_model
    if _client is None:
        from meilisearch import Client as MeilisearchClient
        url = (os.environ.get("MEILISEARCH_URL") or "http://localhost:7700").strip()
        api_key = (os.environ.get("MEILI_MASTER_KEY") or "").strip() or None
        _client = MeilisearchClient(url, api_key=api_key)
        _configure_session(_client)
        # Cache the index object (just a reference, no network call)
        _index = _client.index(HPO_INDEX_UID)
        # Health check: verify Meilisearch is reachable
        try:
            health = _client.health()
            logger.info("Meilisearch health OK: %s — %s", url, health)
        except Exception as exc:
            logger.error("Meilisearch health check FAILED at %s: %s", url, exc)
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
        raise ValueError("Failed to initialize Meilisearch client")
    return _client


def get_index():
    """Return the cached HPO index object. Avoids recreating per call."""
    global _index
    if _index is None:
        _index = get_client().index(HPO_INDEX_UID)
    return _index


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
    index = get_index()

    search_params: dict = {"limit": limit}
    query_vector = _embed_query(search_q) if search_q else None
    if query_vector is not None:
        search_params["vector"] = query_vector
        search_params["hybrid"] = {"embedder": HPO_EMBEDDING_MODEL}

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
        index = get_index()
        search_params: dict = {"limit": limit}
        query_vector = _embed_query(search_q)
        if query_vector is not None:
            search_params["vector"] = f"[{len(query_vector)} dims]"
            search_params["hybrid"] = {"embedder": HPO_EMBEDDING_MODEL}
            # actual params for the call (vector is full list)
            actual_params: dict = {"limit": limit, "vector": query_vector, "hybrid": {"embedder": HPO_EMBEDDING_MODEL}}
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
    # Primary key is "id" with underscore format (HP_0001631)
    doc_id = term_id.strip().replace(":", "_", 1) if ":" in term_id else term_id.strip()
    try:
        index = get_index()
        doc = index.get_document(doc_id)
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
