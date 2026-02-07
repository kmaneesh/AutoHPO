"""
Full-fledged Agno HPO agent: system message, HPO tool (Meilisearch via hpo.py),
history, optional DB. One job: run the agent.
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

from app.hpo import search_hpo

# HPO tool: wrap hpo.search_hpo for the agent (same signature, good docstring for LLM).
def hpo_tool(query: str, limit: int = 10) -> str:
    """
    Search the Human Phenotype Ontology (HPO) by natural language or keyword.
    Use this for any question about phenotypes, clinical features, symptoms, or HPO terms.
    Search by condition description, phenotype name, or HPO ID (e.g. HP:0001631).

    Args:
        query: Search query (e.g. "atrial septal defect", "heart abnormality").
        limit: Maximum number of terms to return (default 10).

    Returns:
        JSON list of HPO terms with hpo_id, name, definition, synonyms_str.
    """
    return search_hpo(query=query, limit=limit)


HPO_SYSTEM_MESSAGE = """\
You are an HPO (Human Phenotype Ontology) assistant that helps users find phenotype terms from natural language descriptions of clinical features, symptoms, or conditions.

## Your responsibilities

1. **Answer phenotype queries** – Use the search tool for any question about phenotypes, HPO terms, clinical findings, or symptom mapping.
2. **Cite HPO IDs** – When presenting results, show HPO ID, name, and a short definition or synonym when helpful.
3. **Acknowledge uncertainty** – If no results are found, say so and suggest rephrasing the query.
4. **No fabrication** – Do not answer from memory; always use the search tool for HPO lookups.

## Guidelines

- For descriptions like "heart defect", "delayed development", or an HPO ID (e.g. HP:0001631), call the search tool with an appropriate query.
- Summarize matching terms clearly. If the user asks for a single term, highlight the best match.
- If the query is ambiguous, you may run the tool with a broad query and then narrow down, or ask the user to clarify.
- Use clear, professional language. You may use markdown for lists and structure.
"""


def get_agent() -> Agent:
    """Build the full-fledged HPO agent with tool, history, and optional DB."""
    model_id = os.environ.get("OPENAI_MODEL_ID", "gpt-4o-mini")
    db = None
    try:
        from agno.db.sqlite import SqliteDb
        db_path = Path(__file__).resolve().parent.parent / "tmp" / "data.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = SqliteDb(db_file=str(db_path))
    except Exception:
        pass

    return Agent(
        name="HPO Agent",
        model=OpenAIChat(id=model_id),
        tools=[hpo_tool],
        system_message=HPO_SYSTEM_MESSAGE,
        add_datetime_to_context=True,
        add_history_to_context=True,
        num_history_runs=5,
        read_chat_history=True,
        enable_agentic_memory=True,
        markdown=True,
        db=db,
    )
