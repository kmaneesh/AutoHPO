"""
MCP server: tools for LLM/MCP clients and GET /api/sse endpoint.
Uses FastMCP 2.x. Run stdio: python -m app.mcp_server. SSE: GET /api/sse (mounted in main).
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    from fastmcp import FastMCP
    _HAS_FASTMCP = True
except ImportError:
    _HAS_FASTMCP = False

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

mcp = FastMCP("AutoHPO") if _HAS_FASTMCP else None

router = APIRouter()


@router.get("/api/sse")
async def api_sse():
    """SSE endpoint for MCP clients."""
    async def event_stream():
        yield "event: connected\ndata: {\"message\": \"AutoHPO MCP\", \"tools\": [\"search_hpo\"]}\n\n"
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _search_hpo_impl(query: str, limit: int = 10) -> str:
    """Call search (regex over in-memory HPO data) with normalized query."""
    from app.search import search, normalize_query
    q = normalize_query(query)
    results = search(query=q or query.strip(), limit=limit)
    return json.dumps(results, indent=2)


if _HAS_FASTMCP and mcp is not None:

    @mcp.tool
    def search_hpo(query: str, limit: int = 10) -> str:
        """
        Search the Human Phenotype Ontology (HPO) by natural language or keyword.
        Use for phenotypes, clinical features, symptoms, or HPO term IDs (e.g. HP:0001631).
        Returns JSON list of terms with hpo_id, name, definition, synonyms_str.
        """
        return _search_hpo_impl(query=query, limit=limit)


def run_stdio():
    """Run the MCP server over stdio (for Cursor/other MCP clients)."""
    if not _HAS_FASTMCP or mcp is None:
        raise RuntimeError("Install FastMCP 2.x: pip install 'fastmcp<3'")
    mcp.run()


if __name__ == "__main__":
    run_stdio()
