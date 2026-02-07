"""
MCP server exposing HPO search (and optionally agent) as tools for LLM/MCP clients.
One job: MCP only. Run as a separate process: python -m app.mcp_server (stdio).
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

mcp = FastMCP("AutoHPO", json_response=True) if _HAS_MCP else None


def _search_hpo_tool(query: str, limit: int = 10) -> str:
    """Call the search funnel (Meilisearch then regex on hp.json)."""
    from app.search import search_funnel
    import json
    results = search_funnel(query=query, limit=limit)
    return json.dumps(results, indent=2)


if _HAS_MCP and mcp is not None:

    @mcp.tool()
    def search_hpo(query: str, limit: int = 10) -> str:
        """
        Search the Human Phenotype Ontology (HPO) by natural language or keyword.
        Use for phenotypes, clinical features, symptoms, or HPO term IDs (e.g. HP:0001631).
        Returns JSON list of terms with hpo_id, name, definition, synonyms_str.
        """
        return _search_hpo_tool(query=query, limit=limit)


def run_stdio():
    """Run the MCP server over stdio (for Cursor/other MCP clients)."""
    if not _HAS_MCP or mcp is None:
        raise RuntimeError("Install mcp to run the MCP server: pip install mcp")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
