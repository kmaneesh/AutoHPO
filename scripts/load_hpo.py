#!/usr/bin/env python3
"""
Parse HPO obographs JSON (data/hp.json), embed terms, push to Meilisearch.
MVP Phase 1: hp.json only.

Creates index: hpo (primary key: id, safe for Meilisearch; hpo_id kept as CURIE for display).

Env:
  MEILISEARCH_URL    – Meilisearch URL (e.g. http://localhost:7700)
  MEILI_MASTER_KEY   – API key if your instance uses one (e.g. masterKey)
  ENABLE_EMBEDDING        – "true" (default) = keyword + embedding search; "false" = keyword-only
  EMBEDDING_MODEL         – sentence-transformers model (default: sentence-transformers/all-MiniLM-L6-v2)
  FORCE_EMBEDDING_DOWNLOAD – "true" to re-download the model (fixes UNEXPECTED position_ids / bad cache)
  REPLACE_INDEX             – "true" or --replace-index to delete existing index and load fresh (no duplicates/stale data)
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
# Primary key must be alphanumeric, hyphen, underscore only (no colon). Use id for Meilisearch; hpo_id for display.
MEILISEARCH_PRIMARY_KEY = "id"
SEARCHABLE_ATTRIBUTES = ["hpo_id", "name", "definition", "synonyms_str"]


def _curie_to_safe_id(curie: str) -> str:
    """Meilisearch document id: only a-z A-Z 0-9, hyphens, underscores (max 511 bytes). hpo_id kept for display."""
    if not curie:
        return ""
    # Replace any character not allowed by Meilisearch with underscore (e.g. : # /)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", curie)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        safe = "unknown"
    if len(safe.encode("utf-8")) > 511:
        safe = safe[:500]
    return safe


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
    """Parse obographs JSON; yield one dict per node with id (safe), hpo_id (CURIE), name, definition, synonyms_str."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise SystemExit(f"Failed to read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {path}: {e}") from e
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
                "id": _curie_to_safe_id(curie),
                "hpo_id": curie,
                "name": name,
                "definition": defn,
                "synonyms_str": synonyms_str,
            })
    return out


def _embedding_enabled() -> bool:
    v = os.environ.get("ENABLE_EMBEDDING", "true").strip().lower()
    return v in ("1", "true", "yes")


def _embedding_model() -> str:
    return os.environ.get(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    ).strip() or "sentence-transformers/all-MiniLM-L6-v2"


def _force_embedding_download() -> bool:
    v = os.environ.get("FORCE_EMBEDDING_DOWNLOAD", "").strip().lower()
    return v in ("1", "true", "yes")


def _replace_index() -> bool:
    v = os.environ.get("REPLACE_INDEX", "").strip().lower()
    return v in ("1", "true", "yes")


def load_hpo(
    json_path: Path,
    meilisearch_url: str,
    api_key: str | None = None,
    index_uid: str = HPO_INDEX_UID,
    embed: bool = True,
    embedding_model: str | None = None,
    force_embedding_download: bool = False,
    replace_index: bool = False,
    batch_size: int = 500,
) -> None:
    if not json_path.exists():
        raise FileNotFoundError(f"HPO JSON not found: {json_path}. Run scripts/download_hpo.py first.")
    if not meilisearch_url.strip():
        raise ValueError("MEILISEARCH_URL is required")

    # Env: ENABLE_EMBEDDING=false => keyword-only; CLI --no-embed overrides
    use_embedding = embed and _embedding_enabled()
    model_id = (embedding_model or _embedding_model()).strip()
    force_download = force_embedding_download or _force_embedding_download()
    do_replace_index = replace_index or _replace_index()

    print(f"Parsing {json_path} ...")
    terms = parse_obographs(json_path)
    print(f"Parsed {len(terms)} terms.")
    print("Search mode: keyword + embedding." if use_embedding else "Search mode: keyword-only (ENABLE_EMBEDDING=false or --no-embed).")

    if use_embedding:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("sentence-transformers not installed; skipping embeddings.", file=sys.stderr)
            use_embedding = False
        else:
            print(f"Loading embedding model ({model_id}) ...")
            if force_download:
                # Re-download into a separate cache to avoid UNEXPECTED position_ids / bad cache
                import tempfile
                print("Force re-downloading model (clean cache for this run). Tip: delete ~/.cache/torch/sentence_transformers to refresh default cache for future runs.")
                with tempfile.TemporaryDirectory(prefix="autohpo_embed_") as tmp_cache:
                    try:
                        model = SentenceTransformer(model_id, cache_folder=tmp_cache)
                    except Exception as e:
                        print(f"Failed to load model {model_id}: {e}", file=sys.stderr)
                        use_embedding = False
                    else:
                        texts = [
                            f"{t['name']}. {t['definition']}. {t['synonyms_str']}".strip() or t["hpo_id"]
                            for t in terms
                        ]
                        print("Computing embeddings ...")
                        try:
                            embeddings = model.encode(texts, show_progress_bar=True)
                            for t, vec in zip(terms, embeddings, strict=True):
                                t["_embedding"] = vec.tolist()
                        except Exception as e:
                            print(f"Embedding failed: {e}", file=sys.stderr)
                            print("Indexing without embeddings (keyword-only).", file=sys.stderr)
                            use_embedding = False
            else:
                try:
                    model = SentenceTransformer(model_id)
                except Exception as e:
                    print(f"Failed to load model {model_id}: {e}", file=sys.stderr)
                    print("Falling back to keyword-only search. Set ENABLE_EMBEDDING=false to skip embedding.", file=sys.stderr)
                    use_embedding = False
                else:
                    texts = [
                        f"{t['name']}. {t['definition']}. {t['synonyms_str']}".strip() or t["hpo_id"]
                        for t in terms
                    ]
                    print("Computing embeddings ...")
                    try:
                        embeddings = model.encode(texts, show_progress_bar=True)
                        for t, vec in zip(terms, embeddings, strict=True):
                            t["_embedding"] = vec.tolist()
                    except Exception as e:
                        print(f"Embedding failed: {e}", file=sys.stderr)
                        print("Indexing without embeddings (keyword-only).", file=sys.stderr)
                        use_embedding = False

    try:
        client = MeilisearchClient(meilisearch_url, api_key=api_key or None)
    except Exception as e:
        print(f"Meilisearch client error: {e}", file=sys.stderr)
        sys.exit(1)
    # Option: delete existing index and load fresh (no stale data, no duplicates from previous runs)
    if do_replace_index:
        try:
            idx = client.get_index(index_uid)
            print(f"Deleting existing index '{index_uid}' (--replace-index) ...")
            task_info = idx.delete()
            idx.wait_for_task(task_info.task_uid, timeout_in_ms=15_000)
        except Exception:
            pass  # index may not exist
    try:
        idx = client.get_index(index_uid)
        idx.fetch_info()
        if getattr(idx, "primary_key", None) != MEILISEARCH_PRIMARY_KEY:
            # Old index had primaryKey hpo_id (invalid due to colon); recreate with id
            print(f"Recreating index {index_uid} with primary key '{MEILISEARCH_PRIMARY_KEY}' (was '{getattr(idx, 'primary_key', None)}') ...")
            task_info = idx.delete()
            idx.wait_for_task(task_info.task_uid, timeout_in_ms=10_000)
            client.create_index(index_uid, {"primaryKey": MEILISEARCH_PRIMARY_KEY})
            idx = client.index(index_uid)
    except Exception:
        client.create_index(index_uid, {"primaryKey": MEILISEARCH_PRIMARY_KEY})
        idx = client.index(index_uid)
    idx.update_searchable_attributes(SEARCHABLE_ATTRIBUTES)

    # Build documents; deduplicate by id so one document per primary key (last wins)
    seen_ids: dict[str, dict] = {}
    for t in terms:
        doc = {
            "id": t["id"],
            "hpo_id": t["hpo_id"],
            "name": t["name"],
            "definition": t["definition"],
            "synonyms_str": t["synonyms_str"],
        }
        if use_embedding and "_embedding" in t:
            doc["_embedding"] = t["_embedding"]
        seen_ids[t["id"]] = doc
    documents = list(seen_ids.values())
    if len(documents) < len(terms):
        print(f"Deduplicated by id: {len(terms)} terms -> {len(documents)} documents (dropped {len(terms) - len(documents)} duplicate ids).")

    # Primary key must be alphanumeric/underscore/hyphen only; id = HP_0000001, hpo_id = HP:0000001 for display

    # Meilisearch indexation is async: we must wait for each task or data may not appear
    timeout_ms = 300_000  # 5 min per batch for large payloads with embeddings
    print(f"Indexing {len(documents)} documents (batch_size={batch_size}) ...")
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        task_info = idx.add_documents(batch)
        task = idx.wait_for_task(task_info.task_uid, timeout_in_ms=timeout_ms)
        if getattr(task, "status", None) == "failed":
            err = getattr(task, "error", None) or {}
            msg = err.get("message", err) if isinstance(err, dict) else err
            print(f"Meilisearch indexation failed: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"  {min(i + batch_size, len(documents))}/{len(documents)}")
    print("Done.")


def _run_load_hpo(args: argparse.Namespace) -> None:
    """Inner load logic for error handling."""
    json_path = args.input or (args.data_dir / "hp.json")
    url = (args.meilisearch_url or "").strip()
    if not url:
        print("Error: set MEILISEARCH_URL or pass --meilisearch-url", file=sys.stderr)
        sys.exit(1)
    api_key = (args.meili_master_key or "").strip() or None
    embed_model = (args.embed_model or "").strip() or None
    load_hpo(
        json_path,
        url,
        api_key=api_key,
        embed=not args.no_embed,
        embedding_model=embed_model,
        force_embedding_download=args.force_embedding_download,
        replace_index=args.replace_index,
        batch_size=args.batch_size,
    )


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
        help="Skip embedding (keyword-only search); overrides ENABLE_EMBEDDING",
    )
    parser.add_argument(
        "--embed-model",
        default=os.environ.get("EMBEDDING_MODEL", ""),
        help="sentence-transformers model (default: EMBEDDING_MODEL or all-MiniLM-L6-v2)",
    )
    parser.add_argument(
        "--force-embedding-download",
        action="store_true",
        help="Re-download embedding model (fixes UNEXPECTED position_ids); overrides FORCE_EMBEDDING_DOWNLOAD",
    )
    parser.add_argument(
        "--replace-index",
        action="store_true",
        help="Delete existing index and load fresh (no stale or duplicate data from previous runs)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Documents per batch (default: 500)",
    )
    args = parser.parse_args()
    try:
        _run_load_hpo(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
