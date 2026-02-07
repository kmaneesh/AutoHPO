# AutoHPO: RAG Stack (Agno + Meilisearch + HTMX/Tailwind/Alpine)

Plan: agent always in the loop; minimal frontend with HTMX, Tailwind CSS, and Alpine.js (no Streamlit, no Node). Search funnel: agent → Meilisearch → regex on hp.json.

---

## TODOs (trackable)

| ID | Task |
|----|------|
| **layout-docker** | Project layout (scripts/, data/, app/ with static/ and templates/), Docker |
| **data-ingestion** | Scripts: download_hpo.py, load_hpo.py (parse, embed, push to Meilisearch) |
| **agent-tool** | Full-fledged Agno agent (knowledge_agent-style) with HPO tool wrapping hpo.py |
| **api-deploy** | web.py routes + main.py: agent, funnel, fallback, health, static/templates |
| **frontend-htmx** | Frontend: HTMX + Tailwind + Alpine, agent-first, fallback to funnel |
| **mcp-server** | MCP server (mcp_server.py) for LLM/MCP clients |
| **readme** | README: structure, stack, data source, quick start |
| **test-refine** | Testing: Relevance tuning and error handling |

---

## 1. Folder structure

```
AutoHPO/
  docker-compose.yml      # Meilisearch service + app service
  Dockerfile             # App image: app/ (includes static + templates), scripts/
  .env.example
  requirements.txt
  data/                  # Cached HPO data (hp.json); optional .gitignore
  scripts/
    download_hpo.py       # Download hp.json from PURL into data/
    load_hpo.py           # Parse obographs, embed terms, push to Meilisearch
  app/
    __init__.py
    main.py               # Composes FastAPI app; mounts web routes, static, templates
    web.py                # All FastAPI routes (/, /health, /api/chat, /api/search/*)
    agent.py              # Full-fledged Agno agent (HPO tool, system message, history, db)
    hpo.py                # Pure Meilisearch: single search_hpo(query, limit) only
    search.py             # Funnel: try agent → Meilisearch (hpo) → regex on data/hp.json
    mcp_server.py         # MCP server exposing search (and optionally agent) for LLM clients
    static/               # HTML/CSS/JS served by FastAPI
      index.html
    templates/            # Server-rendered pages (e.g. Jinja2)
  PLAN.md
  README.md
```

- **app/hpo.py**: Pure Meilisearch. Single function `search_hpo(query, limit)`; no agent, no fallbacks. Used by the agent tool and by the funnel’s second layer.
- **app/agent.py**: Full-fledged Agno agent (see [knowledge_agent](https://github.com/agno-agi/agno/blob/main/cookbook/01_showcase/01_agents/knowledge_agent/agent.py)): system message, tools=[HPO tool wrapping hpo.search_hpo], add_datetime_to_context, add_history_to_context, num_history_runs, read_chat_history, enable_agentic_memory, markdown, optional SqliteDb for chat history.
- **app/search.py**: Funnel. (1) Try agent. (2) Fallback: Meilisearch via hpo.search_hpo. (3) Fallback: regex/search on data/hp.json only (obographs: id, name, definition, synonyms). Returns unified list of HPO term dicts (hpo_id, name, definition, synonyms_str).
- **app/web.py**: All HTTP routes; no business logic—calls agent or search funnel.
- **app/mcp_server.py**: MCP server so LLM clients can use HPO search (and optionally agent) as tools.
- **app/main.py**: Creates app, includes web routes, mounts app/static and app/templates.
- **scripts/download_hpo.py**: Fetch hp.json to data/; idempotent.
- **scripts/load_hpo.py**: Parse obographs, embed, push to Meilisearch; expects MEILISEARCH_URL.

### Data sources (MVP Phase 1 vs Phase 2)

- **MVP Phase 1 – ontology only**: Use **hp.json** only ([obographs JSON](https://obofoundry.org/ontology/hp.html), simple, no reasoner, no imported terms). Sufficient for term-centric search (id, name, definition, synonyms). URL: `https://purl.obolibrary.org/obo/hp.json`.
- **Phase 2 – extended data (later)**:
  - **hp-full.json** (optional): Reasoner-classified ontology including imported terms; use if you need richer hierarchy or cross-ontology links. URL: `https://purl.obolibrary.org/obo/hp/hp-full.json`.
  - **Clinical annotation files**: (1) **phenotype.hpoa** – phenotype → disease (OMIM, Orphanet); (2) **phenotype_to_genes** – phenotype → gene (from [JAX annotations](https://hpo.jax.org/app/data/annotations)). Extend download script and loader to add associated diseases/genes per HPO term in a later phase.

---

## 2. Docker

- **Meilisearch**: Run in its own container via `docker-compose`. Expose port (e.g. 7700); optional volume for persistence. No app code inside this container.
- **App container (one service)**: Agent + FastAPI API + fallback endpoint + static frontend. Same image can run the ingest scripts (e.g. `docker compose run app python scripts/load_hpo.py`) so parsing/embedding/load runs in the same environment as the API. Meilisearch URL passed via env (e.g. `MEILISEARCH_URL=http://meilisearch:7700` when both in same compose network).

Example layout:

- **docker-compose.yml**: `meilisearch` service (image + port + optional volume); `app` service (build from Dockerfile, depends on meilisearch, env for `MEILISEARCH_URL`, mount `data/` and optionally `scripts/` if you run load from host).
- **Dockerfile**: Python base, install requirements, copy `app/`, `static/`, `scripts/`; CMD runs the FastAPI server (e.g. `uvicorn app.main:app`). Scripts are available in the image for one-off ingest runs.

---

## 3. Architecture (Agent + Minimal Frontend)

**Frontend stack**: HTMX + Tailwind CSS + Alpine.js. Agent is always used; fallback is direct Meilisearch when the agent API is unreachable.

- **Agno + FastAPI**: Agent API on FastAPI (`localhost:8000`, `/docs`).
- **Meilisearch**: Hybrid search (keyword + vector); embeddings at ingest only.
- **Data source**: hp.json from `http://purl.obolibrary.org/obo/hp.json` for MVP.
- **Fallback**: FastAPI endpoint (e.g. `POST /api/search/fallback`) queries Meilisearch and returns HTML fragment (HTMX) or JSON (Alpine). Same embedding for query vector as agent path.

### Dual endpoints (when Agno provides FastAPI)

- **Our search**: `/`, `/api/chat`, `/api/search/fallback` (funnel), `/health`—served by web.py.
- **Pure Agno API (future)**: When Agno ships a FastAPI app, mount it under a prefix (e.g. `app.mount("/agno", agno_fastapi_app)`) so power users and MCP can call the raw Agno API. One process, one port.

### MCP server

- **app/mcp_server.py**: Exposes HPO search (and optionally agent) as MCP tools so Cursor/other LLM clients can use AutoHPO (e.g. search_hpo, get_hpo_term). Can call the funnel or hpo.py directly; run as separate process (stdio or HTTP) or wired in main if MCP over HTTP.

### Frontend (HTMX + Tailwind + Alpine)

- **HTMX**: Search form POSTs to agent API (or funnel fallback). Response is an HTML fragment; HTMX swaps it into a target `div`. No SPA.
- **Tailwind CSS**: Via CDN or minimal CLI. Layout, search bar, result cards, loading/error states.
- **Alpine.js**: Loading state, "Using fallback search" banner when agent unreachable, optional debounce.
- **Serving**: FastAPI serves from app/static and app/templates. Same origin; agent and fallback on same backend.

---

## 4. README Fixes

- Fix headings: `## Key Features`, `## The Stack` (proper markdown).
- Fix list formatting: use `-` for feature bullets.
- **The Stack**: Orchestration: Agno; Search: Meilisearch; UI: HTMX, Tailwind CSS, Alpine.js.
- Add: Data source (hp.json PURL, link to HPO downloads), Folder structure and Docker (Meilisearch container + app container), Scripts (download_hpo.py, load_hpo.py), Quick start (e.g. `docker compose up`, run ingest, open UI), Implementation outline (phases below).

---

## 5. TODO Breakdown (for discussion)

### Phase 0 – Project layout and Docker (~30 min)

- **0.1** Create folder structure: `scripts/`, `data/`, `app/`, `static/`.
- **0.2** Add `docker-compose.yml`: Meilisearch service (port 7700, optional volume); app service (build from Dockerfile, env `MEILISEARCH_URL`, mount `data/`).
- **0.3** Add `Dockerfile` for app: Python, install deps, copy `app/`, `static/`, `scripts/`; CMD run FastAPI. Scripts available for ingest (e.g. `docker compose run app python scripts/load_hpo.py`).

### Phase 1 – Data and indexing, MVP (~2 h)

- **1.1** **scripts/download_hpo.py**: Download **hp.json only** from PURL into `data/hp.json`; idempotent (skip if exists/recent).
- **1.2** **scripts/load_hpo.py**: Parse obographs from `data/hp.json` (id, name, definition, synonyms); generate embeddings (sentence-transformers all-MiniLM-L6-v2 or configurable); create Meilisearch index with searchable attributes + vector field; push documents (idempotent upsert by HPO id). Use `MEILISEARCH_URL` from env.
- **1.3** Run ingest: `python scripts/download_hpo.py` then `python scripts/load_hpo.py` (or via app container with Meilisearch on same network).

### Phase 2 – Data expansion, optional (~later)

- **2a** Extend download script: optional hp-full.json; phenotype.hpoa; phenotype_to_genes (JAX).
- **2b** Extend loader: index associated diseases/genes per HPO term (or separate index).

### Phase 3 – Agent (~2 h)

- **3.1** Create Agno agent with system prompt: use search_hpo for any phenotype/HPO question.
- **3.2** Implement search_hpo tool (Meilisearch client, keyword + vector, top-k).
- **3.3** Wire tool into agent; test via Python or /docs.

### Phase 4 – API (~1 h)

- **4.1** Expose agent via Agno FastAPI (e.g. /api/chat or /api/query). App connects to Meilisearch via `MEILISEARCH_URL` (e.g. `http://meilisearch:7700` in Docker).
- **4.2** Add fallback endpoint (e.g. POST /api/search/fallback) that queries Meilisearch; return HTML fragment or JSON.
- **4.3** Serve static HTML from `static/` (FastAPI). Ensure app container can run behind compose with meilisearch.

### Phase 5 – Frontend HTMX + Tailwind + Alpine (~2 h)

- **5.1** Single HTML page: search input, submit, result container; Tailwind for layout and styling.
- **5.2** HTMX: form POST to agent API; target result container; loading/error (hx-post, hx-swap, hx-target, optional hx-indicator).
- **5.3** Fallback: on connection error or 5xx, switch to POST /api/search/fallback; Alpine: "using fallback" banner.
- **5.4** Render agent response or fallback results in same result area (agent: markdown/structured; fallback: list of HPO terms).
- **5.5** Optional: Alpine debounce or button-only submit.

### Phase 6 – README and project hygiene (~30 min)

- **6.1** Fix README: headings (Key Features, The Stack), list formatting.
- **6.2** Update stack to HTMX, Tailwind, Alpine; add Data source (MVP hp.json; Phase 2: hp-full, annotations), Quick start, Implementation outline.
- **6.3** Add requirements.txt; document folder structure, Docker (Meilisearch + app container), and scripts (download_hpo.py, load_hpo.py) in README.

### Phase 7 – Testing and refinement (~1–2 h)

- **7.1** End-to-end agent path: complex query → tool call → HPO terms.
- **7.2** Fallback path: stop agent, confirm UI still returns results.
- **7.3** Tune Meilisearch (attributes, vector weight, top-k).
- **7.4** Error messages and loading states in UI.

---

## 6. Summary

- **Agent**: Always in the loop; one search_hpo tool; system prompt enforces tool use for HPO lookups.
- **Frontend**: HTMX + Tailwind + Alpine, served by FastAPI; no Streamlit, no Node.
- **README**: Fix structure; document stack (HTMX/Tailwind/Alpine), folder structure, Docker (Meilisearch + app), scripts (download + load), data source, quick start, and phases above.
