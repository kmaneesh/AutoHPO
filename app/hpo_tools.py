"""
HPO tools for the agent: search_hpo and get_hpo_term.
Wraps app.hpo (Meilisearch + optional vector search) in the agno Toolkit.
"""
from __future__ import annotations

import json
from typing import Any, List

from agno.tools import Toolkit

from app import hpo


class HPOTools(Toolkit):
    """
    HPOTools is a toolkit for searching the Human Phenotype Ontology (HPO).
    Includes search by query and lookup by term ID.
    """

    def __init__(self, **kwargs: Any):
        tools: List[Any] = [
            self.search_hpo,
            self.get_hpo_term,
        ]
        super().__init__(name="hpo_tools", tools=tools, **kwargs)

    def search_hpo(self, query: str, limit: int = 10) -> str:
        """
        Use this function to search the Human Phenotype Ontology by natural language or keyword.

        Args:
            query (str): Search query (e.g. "atrial septal defect", "tachycardia").
            limit (int): Maximum number of HPO terms to return. Defaults to 10.

        Returns:
            str: JSON list of term dicts with hpo_id, name, definition, synonyms_str, or an error message.
        """
        try:
            return hpo.search_hpo(query=query, limit=limit)
        except Exception as e:
            return f"Error searching HPO for '{query}': {e}"

    def get_hpo_term(self, term_id: str) -> str:
        """
        Use this function to fetch a single HPO term by its ID.

        Args:
            term_id (str): The HPO term ID (e.g. HP:0001631 or HP_0001631).

        Returns:
            str: JSON object with hpo_id, name, definition, synonyms_str, or an error message.
        """
        try:
            term = hpo.get_term_by_id(term_id)
            if term:
                return json.dumps(term, indent=2)
            return f"No HPO term found for ID: {term_id}"
        except Exception as e:
            return f"Error fetching HPO term '{term_id}': {e}"
