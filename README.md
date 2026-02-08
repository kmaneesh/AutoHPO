# AutoHPO

AutoHPO is a minimal-stack RAG solution for clinical researchers and bioinformaticians. It replaces rigid keyword-only HPO search with an agentic pipeline: an Agno agent interprets clinical descriptions and queries Meilisearch (keyword + optional vector search) to return relevant Human Phenotype Ontology terms.

- **Agentic search**: Agno agent with a `search_hpo` tool; interprets natural language and maps to HPO terms.
- **Hybrid search**: Meilisearch for keyword and (optionally) vector search; embeddings at ingest.
- **Resilient**: If the agent is unavailable, the API exposes a direct Meilisearch fallback endpoint.
- **Minimal stack**: Python, FastAPI, HTMX + Tailwind + Alpine (no Node.js); Meilisearch in Docker.
- **Local-first**: Run Meilisearch and the app locally for data privacy.

## The Stack

- **Orchestration**: Agno
- **Search**: Meilisearch
- **API**: FastAPI
- **UI**: HTMX, Tailwind CSS, Alpine.js (planned)
- **Data**: Human Phenotype Ontology ([hp.json](http://purl.obolibrary.org/obo/hp.json), obographs)

## Data source

- **MVP**: [hp.json](http://purl.obolibrary.org/obo/hp.json) (obographs; term-centric).
- **Later**: hp-full.json, [phenotype.hpoa](https://purl.obolibrary.org/obo/hp/phenotype.hpoa), phenotype-to-gene (see [HPO downloads](https://human-phenotype-ontology.github.io/downloads.html)).

## Project layout

```
AutoHPO/
  docker-compose.yml              # App only
  docker-compose.meilisearch.yml  # Meilisearch as shared service
  Dockerfile
  .env.example
  requirements.txt
  data/                           # Cached hp.json
  scripts/
    download_hpo.py               # Fetch hp.json to data/
    load_hpo.py                   # Parse, embed (optional), push to Meilisearch
  app/
    main.py                       # FastAPI, /api/chat, /api/search/fallback
    agent.py                      # Agno agent + search_hpo tool
    search.py                     # Meilisearch client
  static/
    index.html
```

## Quick start

1. **Clone and install**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # set MEILISEARCH_URL, MEILI_MASTER_KEY, etc.
   ```

2. **Start Meilisearch** (shared service)
   ```bash
   docker compose -f docker-compose.meilisearch.yml up -d
   ```

3. **Download and load HPO**
   ```bash
   python scripts/download_hpo.py
   python scripts/load_hpo.py
   ```
   Optional: set `ENABLE_EMBEDDING=false` in `.env` for keyword-only; set `EMBEDDING_MODEL` for a different sentence-transformers model.

4. **Run the app**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Or with Docker: `docker compose up -d` (app uses `MEILISEARCH_URL` from `.env`).

5. **Use the API**
   - Agent: `POST /api/chat` with `{"query": "heart defect"}` (requires `OPENAI_API_KEY`).
   - Fallback: `POST /api/search/fallback` with `{"query": "heart defect"}`.

## Environment (.env)

| Variable | Description |
|----------|-------------|
| `MEILISEARCH_URL` | Meilisearch URL (e.g. `http://localhost:7700`) |
| `MEILI_MASTER_KEY` | Meilisearch API key |
| `ENABLE_EMBEDDING` | `true` (default) = keyword + vector; `false` = keyword-only |
| `EMBEDDING_MODEL` | sentence-transformers model (default: `sentence-transformers/all-MiniLM-L6-v2`) |
| `OPENAI_API_KEY` | For the agent (Phase 3) |
| `OPENAI_MODEL_ID` | Optional; default `gpt-4o-mini` |

## License

See [LICENSE](LICENSE).
