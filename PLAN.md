# AutoHPO: RAG Stack (Agno + Meilisearch + HTMX/Tailwind/Alpine)

Plan: agent always in the loop; minimal frontend with HTMX, Tailwind CSS, and Alpine.js (no Streamlit, no Node). Fallback to direct Meilisearch when the agent API is unreachable.

---

## TODOs (trackable)

| ID | Task |
|----|------|
| **layout-docker** | Project layout (scripts/, data/, app/, static/) and Docker (Meilisearch + app container) |
| **data-ingestion** | Scripts: download_hpo.py (fetch to data/), load_hpo.py (parse, embed, push to Meilisearch) |
| **agent-tool** | Agent: Configure Agno agent with search_hpo tool and HPO system prompt |
| **api-deploy** | API: Expose agent via Agno FastAPI; add fallback Meilisearch endpoint |
| **frontend-htmx** | Frontend: HTMX + Tailwind + Alpine UI with agent-first, fallback to Meilisearch |
| **readme** | README: Fix structure (headings, lists), add stack, data source, quick start |
| **test-refine** | Testing: Relevance tuning and error handling |

---

## 1. Folder structure

```
AutoHPO/
  docker-compose.yml      # Meilisearch service + app service
  Dockerfile             # App image: agent + API + frontend (and scripts for ingest)
  .env.example
  requirements.txt
  data/                  # Cached HPO data (e.g. hp.json); optional .gitignore
  scripts/
    download_hpo.py       # Download hp.json from PURL into data/
    load_hpo.py           # Parse obographs, embed terms, push to Meilisearch
  app/
    __init__.py
    main.py               # FastAPI app: routes, static, agent + fallback endpoints
    agent.py              # Agno agent + search_hpo tool
    search.py             # Meilisearch client (used by agent tool and fallback)
  static/                 # HTML/CSS/JS served by FastAPI
    index.html
  PLAN.md
  README.md
```

- **scripts/download_hpo.py**: Fetch `hp.json` from `http://purl.obolibrary.org/obo/hp.json`, save to `data/hp.json` (or configurable path). Idempotent; can skip if file exists or is recent.
- **scripts/load_hpo.py**: Read `data/hp.json`, parse obographs (id, name, definition, synonyms), generate embeddings, create/update Meilisearch index and push documents. Expects Meilisearch URL (e.g. from env); can be run locally or inside the app container.

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

### Frontend (HTMX + Tailwind + Alpine)  

- **HTMX**: Search form POSTs to agent API (or fallback). Response is an HTML fragment; HTMX swaps it into a target `div`. No SPA.
- **Tailwind CSS**: Via CDN or minimal CLI. Layout, search bar, result cards, loading/error states.
- **Alpine.js**: Loading state, "Using fallback search" banner when agent unreachable, optional debounce.
- **Serving**: FastAPI serves the single HTML page. Same origin; agent and fallback on same backend.

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
