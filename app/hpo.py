"""
Pure Meilisearch HPO search and query normalization (stop words). Single place for all queries.
Used by the agent tool and by the search funnel (second layer).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Collection

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

HPO_INDEX_UID = "hpo"

# Default English stop words for clinical/phenotype queries (App-level, Option A).
# Extend via env or config if needed (e.g. HPO_STOP_WORDS="word1,word2").
DEFAULT_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "are", "was", "were", "been", "be", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
    "can", "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "he", "she", "his", "her", "we", "our", "you", "your", "i", "my", "me",
    "not", "no", "so", "if", "then", "than", "when", "which", "who", "what", "where",
    "into", "through", "during", "before", "after", "above", "below", "between",
})


def remove_stop_words(
    query: str,
    stop_words: Collection[str] | None = None,
    min_word_len: int = 1,
) -> str:
    """
    Remove stop words from the query and collapse whitespace.
    Keeps HPO IDs (e.g. HP:0001631) and clinical terms intact.
    """
    if not (query or "").strip():
        return ""
    stop = stop_words if stop_words is not None else DEFAULT_STOP_WORDS
    tokens = re.findall(r"[^\s]+", query.strip())
    kept = []
    for t in tokens:
        if re.match(r"^HP[_:]\d+", t, re.IGNORECASE):
            kept.append(t)
            continue
        lower = t.lower()
        word = re.sub(r"^[\W_]+|[\W_]+$", "", lower)
        if len(word) >= min_word_len and word not in stop:
            kept.append(t)
    return " ".join(kept).strip()


def prepare_search_query(query: str) -> str:
    """
    Prepare a query for HPO search: remove stop words and normalize space.
    Single entry point; used inside search_hpo so all callers get the same filter.
    """
    normalized = remove_stop_words(query)
    return normalized if normalized else query.strip()


def get_client():
    """Build Meilisearch client from MEILISEARCH_URL and MEILI_MASTER_KEY."""
    from meilisearch import Client as MeilisearchClient
    url = (os.environ.get("MEILISEARCH_URL") or "").strip()
    if not url:
        raise ValueError("MEILISEARCH_URL is not set")
    api_key = (os.environ.get("MEILI_MASTER_KEY") or "").strip() or None
    return MeilisearchClient(url, api_key=api_key)


def search_hpo(query: str, limit: int = 10) -> str:
    """
    Search the Human Phenotype Ontology (HPO) index via Meilisearch only.
    Query is normalized (stop words removed) before search. No agent, no fallbacks.

    Args:
        query: Search query (e.g. "atrial septal defect", "HP:0001631").
        limit: Maximum number of HPO terms to return (default 10).

    Returns:
        JSON string of list of dicts with hpo_id, name, definition, synonyms_str.
    """
    q = prepare_search_query(query)
    client = get_client()
    index = client.index(HPO_INDEX_UID)
    response = index.search(q, {"limit": limit})
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
