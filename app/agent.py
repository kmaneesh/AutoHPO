"""
Agno HPO agent: system message, tools from hpo_tools, history. Defines POST /api/chat.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import re

from fastapi import APIRouter
from pydantic import BaseModel

from app import hpo
from app.hpo_tools import HPOTools

_agent = None

HPO_RESULTS_PER_TERM = 5


class ChatRequest(BaseModel):
    query: str


class HPOMatch(BaseModel):
    medical_term: str
    hpo_id: str
    hpo_name: str
    hpo_definition: str


class TermDebug(BaseModel):
    term: str
    query_sent: str
    hit_count: int
    search_params: dict | None = None
    raw_first_hit_keys: list[str] | None = None
    top_result: dict | None = None
    error: str | None = None


class ChatDebug(BaseModel):
    parsed_terms: list[str]
    agent_raw: str
    term_searches: list[TermDebug]


class ChatResponse(BaseModel):
    response: str
    results: list[HPOMatch] | None = None
    debug: ChatDebug | None = None


HPO_SYSTEM_MESSAGE = """\
You are a Clinical Informatics Specialist extracting phenotypic findings from medical narratives for HPO term search.

## Task
Extract atomic clinical findings from the narrative. Output clean medical terms only—no HPO mapping yet.

## Rules

### 1. Atomic extraction
- One concept per term
- Split compound phrases: "Hypertension and syncope" → "Hypertension", "Syncope"
- Example: "Macrocephaly with developmental delay" → "Macrocephaly", "Developmental delay"

### 2. Deduplication
- Merge repeated concepts with different wording
- "Prominent bronchovascular markings bilaterally" + "Increased bronchovascular markings right parahilar" → "Prominent bronchovascular markings"
- List each unique finding once

### 3. Handle negation (CRITICAL)
- **Exclude** negated findings completely
- Negation markers: no, denies, absent, negative for, without, never, ruled out, no history of
- "No seizures" → omit "Seizures"
- "Denies chest pain" → omit "Chest pain"

### 4. Normalize terms
- Use standard medical terminology when clear
- Colloquial → Medical: "racing heart" → "Tachycardia"
- You may suggest synonyms separately if helpful for search
- Preserve clinically significant qualifiers: "Severe intellectual disability" not just "Intellectual disability"

### 5. Output format
- **Bare terms only**—no parentheses, brackets, or measurements
- Not: "Hepatomegaly (liver 9 cm)" → Just: "Hepatomegaly"
- Not: "Tachycardia (racing heart)" → Just: "Tachycardia"
- Optionally list synonyms as separate entries if they aid search

### 6. Exclude
- Social history, demographics, medications (unless describing a finding)
- **Family history**: ignore "mother had", "family history of", etc.
- Extract only the patient's own findings

### 7. Uncertainty
- Include suspected/possible findings
- Note uncertainty briefly if needed: "Suspected seizure activity"

## Output
Return ONLY a numbered list of clinical terms, one per line. No headers, no extra text, no markdown tables.
Example format:
1. Macrocephaly
2. Developmental delay
3. Tachycardia

"""


def _build_agent():
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.db.sqlite import SqliteDb

    model = OpenAIChat(
        base_url=os.environ.get("OPENAI_BASE_URL", "http://100.74.210.70:1234/v1"),
        id=os.environ.get("OPENAI_MODEL_ID", "qwen2.5-7b-instruct-1m"),
        api_key=os.environ.get("OPENAI_API_KEY", "NA"),
    )
    # Persistent DB for chat history (add_history_to_context); path under project data/
    _root = Path(__file__).resolve().parent.parent
    _db_file = os.environ.get("AGENT_DB_FILE") or "data/agent.db"
    _db_path = _root / _db_file if not Path(_db_file).is_absolute() else Path(_db_file)
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    db = SqliteDb(db_file=str(_db_path))

    return Agent(
        name="HPO Agent",
        model=model,
        tools=[HPOTools()],
        db=db,
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


def _strip_brackets(s: str) -> str:
    """Remove everything in parentheses () or brackets [] and trim."""
    s = (s or "").strip()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\[[^\]]*\]", "", s)
    return s.strip()


def _parse_terms(content: str) -> list[str]:
    """
    Extract medical terms from the agent's response.
    Handles numbered lists ("1. Term"), bullet lists ("- Term", "* Term"),
    bare lines, and markdown tables (first column).
    """
    terms: list[str] = []
    seen: set[str] = set()
    for line in (content or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Markdown table row
        if "|" in line:
            cells = [c.strip() for c in line.split("|")]
            if cells and cells[0] == "" and len(cells) > 1:
                cells = cells[1:]
            if cells and cells[-1] == "" and len(cells) > 1:
                cells = cells[:-1]
            if len(cells) < 1:
                continue
            candidate = _strip_brackets(cells[0])
            # Skip separator rows (---) and header-like rows
            if not candidate or re.match(r"^[-:]+$", candidate) or candidate.lower().startswith("medical"):
                continue
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                terms.append(candidate)
            continue
        # Numbered list: "1. Term" / "1) Term"
        m = re.match(r"^\d+[\.\)]\s+(.+)$", line)
        if m:
            candidate = _strip_brackets(m.group(1))
            if candidate:
                key = candidate.lower()
                if key not in seen:
                    seen.add(key)
                    terms.append(candidate)
            continue
        # Bullet list: "- Term" / "* Term"
        m = re.match(r"^[-*]\s+(.+)$", line)
        if m:
            candidate = _strip_brackets(m.group(1))
            if candidate:
                key = candidate.lower()
                if key not in seen:
                    seen.add(key)
                    terms.append(candidate)
            continue
        # Bare line (skip obvious non-term lines)
        candidate = _strip_brackets(line)
        if candidate and not re.match(r"^(#|here|the |i |note)", candidate, re.IGNORECASE):
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                terms.append(candidate)
    return terms


def _build_hpo_matches(terms: list[str]) -> tuple[list[HPOMatch], list[TermDebug]]:
    """For each term, run hybrid search (Meilisearch). Returns (matches, term_debug_list)."""
    matches: list[HPOMatch] = []
    term_debugs: list[TermDebug] = []
    for term in terms:
        results, search_debug = hpo.search_hpo_results(term, limit=HPO_RESULTS_PER_TERM)
        td = TermDebug(
            term=term,
            query_sent=search_debug.get("query_sent", ""),
            hit_count=search_debug.get("hit_count", 0),
            search_params=search_debug.get("search_params"),
            raw_first_hit_keys=search_debug.get("raw_first_hit_keys"),
            error=search_debug.get("error"),
        )
        if results:
            top = results[0]
            td.top_result = top
            matches.append(HPOMatch(
                medical_term=term,
                hpo_id=top.get("hpo_id", ""),
                hpo_name=top.get("name", ""),
                hpo_definition=top.get("definition", ""),
            ))
        else:
            matches.append(HPOMatch(
                medical_term=term,
                hpo_id="",
                hpo_name="",
                hpo_definition="",
            ))
        term_debugs.append(td)
        logger.info("Term %r → %d hits, top=%s, error=%s", term, td.hit_count, td.top_result, td.error)
    return matches, term_debugs


def init_app() -> None:
    """
    Initialise the agent singleton at app startup.
    Call from FastAPI lifespan to avoid first-request load time.
    """
    get_agent()


router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
def api_chat(body: ChatRequest):
    """Run the HPO agent; parse extracted terms, run hybrid search per term (top-1), return response + flat results."""
    try:
        agent = get_agent()
        run = agent.run(body.query)
        content = getattr(run, "content", None) or str(run)
        response_text = content or ""
        terms = _parse_terms(response_text)
        logger.info("Parsed %d terms from agent: %s", len(terms), terms)
        if terms:
            matches, term_debugs = _build_hpo_matches(terms)
            debug = ChatDebug(parsed_terms=terms, agent_raw=response_text, term_searches=term_debugs)
        else:
            matches = None
            debug = ChatDebug(parsed_terms=[], agent_raw=response_text, term_searches=[])
        return ChatResponse(response=response_text, results=matches, debug=debug)
    except Exception as exc:
        logger.error("api_chat FAILED: %s", exc, exc_info=True)
        return ChatResponse(response="Agent not available. Try normal search.", results=None)
