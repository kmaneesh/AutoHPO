"""
Tests for app.hpo: query helpers (stop words) and Meilisearch search.
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


# --- Query helpers (moved to hpo.py) ---

def test_remove_stop_words_empty():
    from app.hpo import remove_stop_words
    assert remove_stop_words("") == ""
    assert remove_stop_words("   ") == ""


def test_remove_stop_words_basic():
    from app.hpo import remove_stop_words
    assert remove_stop_words("the patient has a heart defect") == "patient heart defect"
    assert remove_stop_words("and or but in on at") == ""


def test_remove_stop_words_preserves_hpo_id():
    from app.hpo import remove_stop_words
    assert remove_stop_words("HP:0001631") == "HP:0001631"
    assert remove_stop_words("find HP_0001631 and atrial defect") == "find HP_0001631 atrial defect"


def test_remove_stop_words_collapse_whitespace():
    from app.hpo import remove_stop_words
    assert remove_stop_words("  atrial   septal   defect  ") == "atrial septal defect"


def test_remove_stop_words_custom_stop_list():
    from app.hpo import remove_stop_words
    assert remove_stop_words("heart defect", stop_words={"heart"}) == "defect"


def test_prepare_search_query_returns_original_if_empty_after_stop_words():
    from app.hpo import prepare_search_query
    assert prepare_search_query("  the and or  ") == "the and or"


def test_prepare_search_query_normalizes():
    from app.hpo import prepare_search_query
    assert prepare_search_query("the patient with atrial septal defect") == "patient atrial septal defect"


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
        """Query with stop words is normalized before search (no error, same path)."""
        from app.hpo import search_hpo
        result = search_hpo("the patient with a heart defect", limit=3)
        data = json.loads(result)
        assert isinstance(data, list)


def test_search_funnel_uses_hpo_normalization():
    """search_funnel passes query to search_hpo (which normalizes internally)."""
    from app.search import search_funnel
    with patch("app.search.search_hpo") as mock_hpo:
        mock_hpo.return_value = "[]"
        search_funnel("the patient has a heart defect", limit=5)
        call_args = mock_hpo.call_args
        assert call_args is not None
        # search_hpo receives raw query; it normalizes internally
        assert "heart" in call_args.kwargs["query"] or "patient" in call_args.kwargs["query"]


@pytest.mark.skipif(
    not (ROOT / "data" / "hp.json").exists(),
    reason="data/hp.json not found (run download_hpo.py)",
)
def test_regex_search_hp_json_returns_list():
    from app.search import regex_search_hp_json
    results = regex_search_hp_json("heart", limit=3)
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


def test_search_funnel_with_test_cases(test_case_queries):
    """Run search_funnel on first 5 test case excerpts; check valid structure."""
    from app.search import search_funnel
    for case_id, query in test_case_queries:
        results = search_funnel(query, limit=10)
        assert isinstance(results, list)
        for item in results:
            assert "hpo_id" in item
            assert "name" in item
