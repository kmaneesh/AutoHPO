#!/usr/bin/env python3
"""
Parse HPO obographs JSON (data/hp.json), embed terms, push to Meilisearch.
MVP Phase 1: hp.json only.

Creates index: hpo (primary key: hpo_id).

Env:
  MEILISEARCH_URL   – Meilisearch URL (e.g. http://localhost:7700)
  MEILI_MASTER_KEY  – API key if your instance uses one (e.g. masterKey)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Load .env from project root so MEILISEARCH_URL / MEILI_MASTER_KEY are set when run as script
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    from meilisearch import Client as MeilisearchClient
except ImportError:
    print("Install meilisearch: pip install meilisearch", file=sys.stderr)
    sys.exit(1)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HPO_INDEX_UID = "hpo"
SEARCHABLE_ATTRIBUTES = ["hpo_id", "name", "definition", "synonyms_str"]

# From env with defaults (must match app.hpo and index embedder settings)
HPO_EMBEDDER_NAME = (os.environ.get("HPO_EMBEDDER_NAME") or "hpo-semantic").strip()
HPO_EMBEDDING_DIMENSIONS = int(os.environ.get("HPO_EMBEDDING_DIMENSIONS", "384"))
HPO_EMBEDDING_MODEL = (os.environ.get("HPO_EMBEDDING_MODEL") or "all-MiniLM-L6-v2").strip()


def _curie_from_id(node_id: str) -> str:
    """Convert OBO IRI to CURIE (e.g. http://.../HP_0000123 -> HP:0000123)."""
    if not node_id:
        return ""
    if "://" in node_id:
        # .../obo/HP_0000123 or .../obo/hp/HP_0000123
        part = node_id.split("/")[-1]
        if "_" in part:
            ns, rest = part.split("_", 1)
            return f"{ns.upper()}:{rest}"
        return part
    return node_id.replace("_", ":", 1) if "_" in node_id else node_id


def parse_obographs(path: Path) -> list[dict]:
    """Parse obographs JSON; yield one dict per node with hpo_id, name, definition, synonyms_str."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for graph in data.get("graphs", []):
        for node in graph.get("nodes", []):
            node_id = node.get("id") or ""
            curie = _curie_from_id(node_id)
            name = (node.get("lbl") or "").strip()
            meta = node.get("meta") or {}
            defn = ""
            if isinstance(meta.get("definition"), dict):
                defn = (meta["definition"].get("val") or "").strip()
            synonyms = []
            for s in meta.get("synonyms", []):
                if isinstance(s, dict) and s.get("val"):
                    synonyms.append(str(s["val"]).strip())
            synonyms_str = " | ".join(synonyms) if synonyms else ""
            out.append({
                "hpo_id": curie,
                "name": name,
                "definition": defn,
                "synonyms_str": synonyms_str,
            })
    return out


def load_hpo(
    json_path: Path,
    meilisearch_url: str,
    api_key: str | None = None,
    index_uid: str = HPO_INDEX_UID,
    embed: bool = True,
    batch_size: int = 500,
) -> None:
    if not json_path.exists():
        raise FileNotFoundError(f"HPO JSON not found: {json_path}. Run scripts/download_hpo.py first.")
    if not meilisearch_url.strip():
        raise ValueError("MEILISEARCH_URL is required")

    print(f"Parsing {json_path} ...")
    terms = parse_obographs(json_path)
    print(f"Parsed {len(terms)} terms.")

    # Env ENABLE_EMBEDDING=false or 0 disables embedding when running load_hpo (same as --no-embed)
    enable_embedding = os.environ.get("ENABLE_EMBEDDING", "true").strip().lower() in ("true", "1", "yes")
    if embed and not enable_embedding:
        embed = False
        print("ENABLE_EMBEDDING is false; skipping embeddings.", file=sys.stderr)

    if embed:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("sentence-transformers not installed; skipping embeddings.", file=sys.stderr)
            embed = False
        else:
            print(f"Loading embedding model ({HPO_EMBEDDING_MODEL}) ...")
            model = SentenceTransformer(HPO_EMBEDDING_MODEL)
            texts = [
                f"{t['name']}. {t['definition']}. {t['synonyms_str']}".strip() or t["hpo_id"]
                for t in terms
            ]
            print("Computing embeddings ...")
            embeddings = model.encode(texts, show_progress_bar=True)
            for t, vec in zip(terms, embeddings, strict=True):
                t["_embedding"] = vec.tolist()

    client = MeilisearchClient(meilisearch_url, api_key=api_key or None)
    try:
        client.get_index(index_uid)
    except Exception:
        client.create_index(index_uid, {"primaryKey": "hpo_id"})
    idx = client.index(index_uid)
    idx.update_searchable_attributes(SEARCHABLE_ATTRIBUTES)

    # Configure user-provided embedder for vector search (must match document _vectors key)
    if embed:
        task = idx.update_settings({
            "embedders": {
                HPO_EMBEDDER_NAME: {
                    "source": "userProvided",
                    "dimensions": HPO_EMBEDDING_DIMENSIONS,
                }
            }
        })
        # Wait for embedder config so documents with _vectors are accepted
        if hasattr(client, "wait_for_task") and isinstance(task, dict) and task.get("taskUid") is not None:
            client.wait_for_task(task["taskUid"])

    # Meilisearch expects primary key in each document; use hpo_id as unique id.
    # Vector search uses _vectors[embedder_name], not _embedding.
    documents = []
    for t in terms:
        doc = {"hpo_id": t["hpo_id"], "name": t["name"], "definition": t["definition"], "synonyms_str": t["synonyms_str"]}
        if embed and "_embedding" in t:
            doc["_vectors"] = {HPO_EMBEDDER_NAME: t["_embedding"]}
        documents.append(doc)

    print(f"Indexing {len(documents)} documents (batch_size={batch_size}) ...")
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        idx.add_documents(batch)
        print(f"  {min(i + batch_size, len(documents))}/{len(documents)}")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load HPO from data/hp.json into Meilisearch")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing hp.json (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to hp.json (overrides --data-dir/hp.json)",
    )
    parser.add_argument(
        "--meilisearch-url",
        default=os.environ.get("MEILISEARCH_URL", ""),
        help="Meilisearch URL (default: MEILISEARCH_URL env)",
    )
    parser.add_argument(
        "--meili-master-key",
        default=os.environ.get("MEILI_MASTER_KEY", ""),
        help="Meilisearch API key (default: MEILI_MASTER_KEY env)",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip embedding (keyword-only search)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Documents per batch (default: 500)",
    )
    args = parser.parse_args()
    json_path = args.input or (args.data_dir / "hp.json")
    url = (args.meilisearch_url or "").strip()
    if not url:
        print("Error: set MEILISEARCH_URL or pass --meilisearch-url", file=sys.stderr)
        sys.exit(1)
    api_key = (args.meili_master_key or "").strip() or None
    load_hpo(json_path, url, api_key=api_key, embed=not args.no_embed, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
