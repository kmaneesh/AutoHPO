"""
Pytest fixtures. Test_Cases.csv path from env RAG_HPO_TEST_CASES or default.
"""
from pathlib import Path

import pytest

# Default path to RAG-HPO test cases (optional; tests skip if missing)
DEFAULT_TEST_CASES_CSV = Path("/Users/m/Downloads/RAG-HPO-main/Test_Cases.csv")


def _get_test_cases_path() -> Path:
    import os
    return Path(os.environ.get("RAG_HPO_TEST_CASES", str(DEFAULT_TEST_CASES_CSV)))


@pytest.fixture(scope="session")
def test_cases_csv_path() -> Path:
    return _get_test_cases_path()


@pytest.fixture(scope="session")
def test_cases_available(test_cases_csv_path: Path) -> bool:
    return test_cases_csv_path.exists() and test_cases_csv_path.is_file()
