"""
Tests for app.hpo: query helpers (whitespace normalization) and Meilisearch search.
Runs against actual Meilisearch when available; acceptance criteria defined below.
Uses Test_Cases.csv when RAG_HPO_TEST_CASES is set or file exists at default path.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Project root
ROOT = Path(__file__).resolve().parent.parent

# --- Acceptance criteria for real Meilisearch tests ---
# Minimum number of hits we expect for known-good queries (index must be loaded).
MIN_HITS_ACCEPTANCE = 1
# For "atrial septal defect" we expect this HPO ID in top results (if index is HPO).
EXPECTED_HPO_ID_FOR_ATRIAL = "HP:0001631"
# Queries that should return at least MIN_HITS_ACCEPTANCE when index is populated.
ACCEPTANCE_QUERIES = [
    "atrial septal defect",
    "heart defect",
    "HP:0001631",
]


# --- Query helpers (whitespace normalization only; no stop-word removal) ---

def test_prepare_search_query_empty():
    from app.hpo import prepare_search_query
    assert prepare_search_query("") == ""
    assert prepare_search_query("   ") == ""


def test_prepare_search_query_normalizes_whitespace():
    from app.hpo import prepare_search_query
    assert prepare_search_query("  atrial   septal   defect  ") == "atrial septal defect"
    assert prepare_search_query("the patient with atrial septal defect") == "the patient with atrial septal defect"


# --- Meilisearch client ---

def test_get_client_raises_when_url_unset():
    from app.hpo import get_client
    with patch.dict(os.environ, {"MEILISEARCH_URL": ""}, clear=False):
        with pytest.raises(ValueError, match="MEILISEARCH_URL"):
            get_client()


# --- Real Meilisearch acceptance tests ---

def _meilisearch_available() -> bool:
    url = (os.environ.get("MEILISEARCH_URL") or "").strip()
    if not url:
        return False
    try:
        from app.hpo import get_client
        client = get_client()
        client.health()
        return True
    except Exception:
        return False


def _hpo_index_has_documents() -> bool:
    try:
        from app.hpo import get_client, HPO_INDEX_UID
        client = get_client()
        idx = client.get_index(HPO_INDEX_UID)
        stats = idx.get_stats()
        return (stats.get("numberOfDocuments") or 0) > 0
    except Exception:
        return False


@pytest.mark.skipif(
    not _meilisearch_available(),
    reason="Meilisearch not available (set MEILISEARCH_URL and run Meilisearch)",
)
class TestHPOSearchReal:
    """Tests that run against actual Meilisearch. Index must exist and be loaded."""

    def test_search_hpo_returns_valid_json_structure(self):
        from app.hpo import search_hpo
        result = search_hpo("heart", limit=5)
        data = json.loads(result)
        assert isinstance(data, list)
        for item in data:
            assert "hpo_id" in item
            assert "name" in item
            assert "definition" in item
            assert "synonyms_str" in item

    @pytest.mark.skipif(
        not _hpo_index_has_documents(),
        reason="HPO index empty (run scripts/load_hpo.py)",
    )
    def test_search_hpo_acceptance_min_hits(self):
        """Acceptance: known queries return at least MIN_HITS_ACCEPTANCE hits."""
        from app.hpo import search_hpo
        for query in ACCEPTANCE_QUERIES:
            result = search_hpo(query, limit=10)
            data = json.loads(result)
            assert len(data) >= MIN_HITS_ACCEPTANCE, f"Query '{query}' returned {len(data)} hits"

    @pytest.mark.skipif(
        not _hpo_index_has_documents(),
        reason="HPO index empty (run scripts/load_hpo.py)",
    )
    def test_search_hpo_acceptance_atrial_septal_defect(self):
        """Acceptance: 'atrial septal defect' returns HP:0001631 in top results."""
        from app.hpo import search_hpo
        result = search_hpo("atrial septal defect", limit=15)
        data = json.loads(result)
        hpo_ids = [t.get("hpo_id") for t in data]
        assert EXPECTED_HPO_ID_FOR_ATRIAL in hpo_ids, (
            f"Expected {EXPECTED_HPO_ID_FOR_ATRIAL} in {hpo_ids}"
        )

    def test_search_hpo_normalizes_query(self):
        """Query is whitespace-normalized before search (no error, same path)."""
        from app.hpo import search_hpo
        result = search_hpo("the patient with a heart defect", limit=3)
        data = json.loads(result)
        assert isinstance(data, list)


def test_search_returns_list_normalized():
    """search with normalized query returns list of term dicts."""
    from app.search import search, normalize_query
    q = normalize_query("heart")
    results = search(query=q or "heart", limit=5)
    assert isinstance(results, list)
    for item in results:
        assert "hpo_id" in item and "name" in item


@pytest.mark.skipif(
    not (ROOT / "data" / "hp.json").exists(),
    reason="data/hp.json not found (run download_hpo.py)",
)
def test_search_returns_list():
    """search.search returns list of term dicts when hp.json is loaded."""
    from app import search as search_module
    search_module.init_app()
    results = search_module.search("heart", limit=3)
    assert isinstance(results, list)
    for item in results:
        assert "hpo_id" in item
        assert "name" in item
        assert "definition" in item
        assert "synonyms_str" in item


# --- Test_Cases.csv ---

def _load_test_case_queries(csv_path: Path, max_cases: int = 5) -> list[tuple[str, str]]:
    out = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= max_cases:
                break
            case = row.get("Case", "")
            note = (row.get("clinical_note") or "").strip()
            if note:
                out.append((case, note[:200]))
    return out


@pytest.fixture(scope="module")
def test_case_queries(test_cases_csv_path: Path):
    if not test_cases_csv_path.exists() or not test_cases_csv_path.is_file():
        pytest.skip("Test_Cases.csv not found; set RAG_HPO_TEST_CASES or add file at default path")
    return _load_test_case_queries(test_cases_csv_path, max_cases=5)


def test_search_with_test_cases(test_case_queries):
    """Run search (normalized query) on first 5 test case excerpts; check valid structure."""
    from app.search import search, normalize_query
    for case_id, query in test_case_queries:
        q = normalize_query(query)
        results = search(query=q or query.strip(), limit=10)
        assert isinstance(results, list)
        for item in results:
            assert "hpo_id" in item
            assert "name" in item
