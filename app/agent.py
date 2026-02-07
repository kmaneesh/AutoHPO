"""
Full-fledged Agno HPO agent: system message, HPOTools, history. One job: run the agent.
Defines POST /api/chat. Agent is initialised once (singleton).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.hpo import search_hpo

# Lazy singleton; initialised once on first get_agent() call
_agent = None


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


def _format_search_results_as_response(results: list) -> str:
    """Format search funnel results as plain text for ChatResponse."""
    if not results:
        return "No HPO terms found."
    lines = ["**Search results (HPO):**", ""]
    for t in results:
        lines.append(f"- **{t.get('hpo_id', '')}** {t.get('name', '')}")
        if t.get("definition"):
            lines.append(f"  {str(t['definition'])[:200]}…")
        lines.append("")
    return "\n".join(lines).strip()


# --- Agno agent (import here to avoid circular deps; build after router)
def _build_agent():
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools import Toolkit

    class HPOTools(Toolkit):
        def __init__(self, **kwargs: Any):
            tools: List[Any] = [self.search_hpo, self.get_hpo_term]
            super().__init__(name="hpo_tools", tools=tools, **kwargs)

        def search_hpo(self, query: str, limit: int = 10) -> str:
            try:
                return search_hpo(query=query, limit=limit)
            except Exception as e:
                return f"Error searching HPO for '{query}': {e}"

        def get_hpo_term(self, term_id: str) -> str:
            try:
                q = term_id.strip().replace("_", ":", 1) if "_" in term_id else term_id.strip()
                raw = search_hpo(query=q, limit=1)
                results = json.loads(raw)
                if results:
                    return json.dumps(results[0], indent=2)
                return f"No HPO term found for ID: {term_id}"
            except Exception as e:
                return f"Error fetching HPO term '{term_id}': {e}"

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

    model = OpenAIChat(
        base_url=os.environ.get("OPENAI_BASE_URL", "http://100.72.226.65:1234/v1"),
        id=os.environ.get("OPENAI_MODEL_ID", "qwen2.5-7b-instruct-1m"),
        api_key=os.environ.get("OPENAI_API_KEY", "NA"),
    )
    return Agent(
        name="HPO Agent",
        model=model,
        tools=[HPOTools()],
        system_message=HPO_SYSTEM_MESSAGE,
        add_datetime_to_context=True,
        add_history_to_context=True,
        num_history_runs=5,
        read_chat_history=True,
        enable_agentic_memory=True,
        markdown=True,
    )


def get_agent():
    """Return the singleton agent; initialise once on first call."""
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def init_app() -> None:
    """
    Initialise the agent singleton at app startup.
    Call from FastAPI lifespan to avoid first-request load time.
    """
    get_agent()


router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
def api_chat(body: ChatRequest):
    """Run the HPO agent; if LLM is unavailable, fall back to pure search."""
    try:
        agent = get_agent()
        run = agent.run(body.query)
        content = getattr(run, "content", None) or str(run)
        return ChatResponse(response=content or "")
    except Exception:
        try:
            from app.search import search_funnel
            results = search_funnel(query=body.query, limit=15)
            text = _format_search_results_as_response(results)
            return ChatResponse(response=f"*Agent unavailable. Using search:*\n\n{text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
