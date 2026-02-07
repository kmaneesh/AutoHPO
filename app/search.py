"""
Meilisearch client for HPO index. Used by the agent tool and fallback endpoint.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

HPO_INDEX_UID = "hpo"


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
    Search the Human Phenotype Ontology (HPO) index by natural language or keyword.

    Use this function whenever the user asks about phenotypes, clinical features,
    symptoms, or HPO terms. Search by condition description, phenotype name, or HPO ID.

    Args:
        query: Search query (e.g. "atrial septal defect", "HP:0001631", "heart abnormality").
        limit: Maximum number of HPO terms to return (default 10).

    Returns:
        JSON string of matching HPO terms with hpo_id, name, definition, synonyms_str.
    """
    client = get_client()
    index = client.index(HPO_INDEX_UID)
    response = index.search(query, {"limit": limit})
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
