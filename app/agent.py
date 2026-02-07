"""
Agno agent with search_hpo tool for HPO term search. Phase 3.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app.search import search_hpo

HPO_SYSTEM_PROMPT = """You are an assistant that helps users find Human Phenotype Ontology (HPO) terms from natural language descriptions of phenotypes, clinical features, or symptoms.

You MUST use the search_hpo tool for any question about phenotypes, HPO terms, clinical findings, or symptom mapping. Do not answer from memory—always search the HPO index.

When the user describes a condition or symptom (e.g. "heart defect", "delayed development", "HP:0001631"), call search_hpo with an appropriate query. Then summarize the matching HPO terms clearly: show the HPO ID, name, and a short definition or synonym when helpful. If no results are found, say so and suggest rephrasing the query."""


def get_agent() -> Agent:
    """Build the HPO search agent with search_hpo tool."""
    model_id = os.environ.get("OPENAI_MODEL_ID", "gpt-4o-mini")
    return Agent(
        model=OpenAIChat(id=model_id),
        tools=[search_hpo],
        instructions=[HPO_SYSTEM_PROMPT],
        markdown=True,
    )
