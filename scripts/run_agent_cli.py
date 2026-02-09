#!/usr/bin/env python3
"""
Run the HPO agent from the command line (same code path as POST /api/chat).
Use inside Docker: docker compose run --rm app python scripts/run_agent_cli.py "your query"
Or with stdin: echo "atrial septal defect" | docker compose run -T --rm app python scripts/run_agent_cli.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root (so "import app" works when run as scripts/run_agent_cli.py)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Load env and init app components (same as FastAPI lifespan)
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from app import agent, search

search.init_app()
agent.init_app()


def main() -> None:
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:]).strip()
    else:
        query = (sys.stdin.read() or "").strip()

    if not query:
        print("Usage: python scripts/run_agent_cli.py <query>", file=sys.stderr)
        print("   or: echo 'your query' | python scripts/run_agent_cli.py", file=sys.stderr)
        sys.exit(1)

    a = agent.get_agent()
    run = a.run(query)
    content = getattr(run, "content", None) or str(run)
    print(content or "")


if __name__ == "__main__":
    main()
