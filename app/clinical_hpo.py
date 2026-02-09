"""
Clinical case → HPO term matching strategy.

Two-stage approach:
  1. Extract phenotypic observations from narrative (placeholder: simple split; LLM/NLP to be plugged in).
  2. Build search query from HPO-oriented terms/IDs (not raw narrative). Keyword/ID is backbone; vector is supplement.

Use clinical_to_hpo_search_query() to get a query string suitable for search_hpo() when processing clinical text.
"""
from __future__ import annotations

import re
from typing import List


def extract_phenotypes(narrative: str) -> List[str]:
    """
    Extract distinct phenotypic observations from clinical narrative.

    Placeholder: returns non-empty phrases from sentence-like splits and strips
    very short fragments. Replace with LLM/NLP (e.g. "list phenotypic findings")
    or rule-based NER for production.

    Goal: symptoms, physical findings, test results, morphology; strip
    demographics, procedures, family history context.
    """
    if not (narrative or "").strip():
        return []
    text = narrative.strip()
    # Simple split on sentence boundaries and newlines; keep phrases with content
    parts = re.split(r"[.\n]+", text)
    phenotypes = []
    for p in parts:
        p = p.strip()
        if len(p) > 2 and not p.lower().startswith(("the patient", "patient has", "history of")):
            phenotypes.append(p)
    return phenotypes if phenotypes else [text]


def clinical_to_hpo_search_query(
    narrative: str,
    *,
    extract_first: bool = False,
    prefer_hpo_ids: bool = False,
) -> str:
    """
    Build a search query from clinical narrative for use with search_hpo().

    - If extract_first=True: extract phenotypes then join with spaces (HPO mapping
      layer can be added later to replace phrases with HPO IDs/labels).
    - If prefer_hpo_ids=True: reserved for future: pass through only HPO IDs
      (e.g. HP:0001513 HP:0100751) when mapping layer is implemented.
    - Otherwise: return narrative as-is (current behaviour; caller normalizes in search_hpo).

    Vector search in search_hpo is supplementary; keyword/ID matching is the backbone
    for clinical→HPO (see docs/CLINICAL_HPO_STRATEGY.md).
    """
    if prefer_hpo_ids:
        # Future: filter to only HPO IDs from mapping layer; for now ignore
        pass
    if extract_first:
        phenotypes = extract_phenotypes(narrative)
        return " ".join(phenotypes).strip() if phenotypes else narrative.strip()
    return (narrative or "").strip()
