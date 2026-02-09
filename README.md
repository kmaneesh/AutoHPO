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
  docker-compose.yml              # Development: App + Meilisearch
  server.yml                      # Production: App only (connects to external Meilisearch)
  Dockerfile
  .env.example
  requirements.txt
  data/                           # Cached hp.json
  scripts/
    download_hpo.py               # Fetch hp.json to data/
    load_hpo.py                   # Parse, embed (optional), push to Meilisearch
  app/
    main.py                       # FastAPI, /api/chat, /api/search
    agent.py                      # Agno agent + HPO tools
    search.py                     # In-memory HPO search
    hpo.py                        # Meilisearch client
  static/
    index.html
```

## Docker Compose Files

- **`docker-compose.yml`**: Development setup with both app and Meilisearch services
- **`server.yml`**: Production setup with app only, connects to existing Meilisearch on localhost:7700

## Quick start

### Development (with Docker)

1. **Clone and configure**
   ```bash
   git clone <repo-url>
   cd AutoHPO
   cp .env.example .env   # Edit: set MEILI_MASTER_KEY, OPENAI_BASE_URL, etc.
   ```

2. **Start services**
   ```bash
   docker compose up -d
   ```

3. **Download and load HPO data**
   ```bash
   python scripts/download_hpo.py
   python scripts/load_hpo.py
   ```

4. **Access the app**
   - Web UI: http://localhost:8000
   - API: http://localhost:8000/docs

### Production (external Meilisearch)

If you already have Meilisearch running on localhost:7700:

1. **Configure**
   ```bash
   cp .env.example .env
   # Ensure MEILISEARCH_URL=http://localhost:7700 (default)
   # Set MEILI_MASTER_KEY to match your Meilisearch instance
   ```

2. **Start app only**
   ```bash
   docker compose -f server.yml up -d
   ```

3. **Load HPO data** (if not already loaded)
   ```bash
   python scripts/download_hpo.py
   python scripts/load_hpo.py
   ```

### Local development (without Docker)

1. **Install dependencies**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start Meilisearch** (using Docker)
   ```bash
   docker run -d -p 7700:7700 \
     -e MEILI_MASTER_KEY=masterKey \
     getmeili/meilisearch:v1.35.0
   ```

3. **Run the app**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

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
