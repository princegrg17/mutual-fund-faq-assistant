"""Phase 3 (indexing) — embed chunks with BGE → Chroma, write SQLite fact store.

Reads ``data/chunks.json`` (Phase 3 chunking) and ``data/facts.json`` (Phase 2)
and writes the two artifacts the query pipeline consumes:

- **Vector index** (Chroma at ``data/chroma/``): BGE embeddings of every chunk,
  upserted by ``chunk_id``. Passages are embedded **plainly** — the BGE search
  instruction prefix is applied to the *query* only, at query time (edgecase C2).
  The embed model id is stored in collection metadata so a query-time mismatch is
  detectable (C3).
- **Fact store** (SQLite at ``data/facts.db``): deterministic ``(scheme_id, field)``
  lookups for numeric facts, ``INSERT OR REPLACE`` so re-ingestion is idempotent.

Run:  python -m ingest.build_index
"""
from __future__ import annotations

import json
import sqlite3
import sys

import chromadb
from sentence_transformers import SentenceTransformer

from config import CHROMA_DIR, DATA_DIR, FACTS_DB, ensure_dirs, settings

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

CHUNKS_JSON = DATA_DIR / "chunks.json"
FACTS_JSON = DATA_DIR / "facts.json"
COLLECTION_NAME = "mf_chunks"

# Chroma metadata values must be scalars; flatten list fields for storage.
_LIST_META_KEYS = ("field_tags",)


def _flatten_meta(meta: dict) -> dict:
    out = {}
    for k, v in meta.items():
        if k in ("text", "display"):
            continue
        if isinstance(v, list):
            out[k] = ", ".join(map(str, v))
        elif v is None:
            out[k] = ""
        else:
            out[k] = v
    return out


def _load_chunks() -> list[dict]:
    if not CHUNKS_JSON.exists():
        sys.exit(f"Missing {CHUNKS_JSON} — run `python -m ingest.chunk` first.")
    return json.loads(CHUNKS_JSON.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Embedding + Chroma
# --------------------------------------------------------------------------- #
def build_vector_index(chunks: list[dict]) -> None:
    print(f"Loading BGE embedding model: {settings.embed_model}")
    model = SentenceTransformer(settings.embed_model)

    passages = [c["text"] for c in chunks]          # embed plainly (no prefix)
    ids = [c["chunk_id"] for c in chunks]
    documents = [c["display"] for c in chunks]      # what the answer layer reads
    metadatas = [_flatten_meta(c) for c in chunks]

    print(f"Embedding {len(passages)} chunks (normalized) ...")
    embeddings = model.encode(
        passages,
        normalize_embeddings=True,   # cosine similarity via normalized vectors
        show_progress_bar=False,
        convert_to_numpy=True,
    ).tolist()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Rebuild cleanly so stale chunks never linger; idempotent re-runs.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:  # noqa: BLE001 — collection may not exist yet
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "embed_model": settings.embed_model,
            "hnsw:space": "cosine",
            "query_prefix": "Represent this sentence for searching relevant passages: ",
        },
    )
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    dim = len(embeddings[0]) if embeddings else 0
    print(f"Chroma collection '{COLLECTION_NAME}': {collection.count()} vectors "
          f"(dim={dim}) → {CHROMA_DIR}")


# --------------------------------------------------------------------------- #
# SQLite fact store
# --------------------------------------------------------------------------- #
def build_fact_store() -> None:
    if not FACTS_JSON.exists():
        sys.exit(f"Missing {FACTS_JSON} — run `python -m ingest.extract` first.")
    records = json.loads(FACTS_JSON.read_text(encoding="utf-8"))

    conn = sqlite3.connect(FACTS_DB)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                scheme_id   TEXT NOT NULL,
                scheme_name TEXT,
                category    TEXT,
                field       TEXT NOT NULL,
                value       TEXT,
                source_url  TEXT,
                fetched_at  TEXT,
                PRIMARY KEY (scheme_id, field)
            )
        """)
        conn.executemany(
            """INSERT OR REPLACE INTO facts
               (scheme_id, scheme_name, category, field, value, source_url, fetched_at)
               VALUES (?,?,?,?,?,?,?)""",
            [(r["scheme_id"], r["scheme_name"], r.get("category"), r["field"],
              r["value"], r["source_url"], r.get("fetched_at")) for r in records],
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        n_nonnull = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE value IS NOT NULL").fetchone()[0]
    finally:
        conn.close()
    print(f"SQLite fact store: {n} rows ({n_nonnull} non-null) → {FACTS_DB}")


def run() -> None:
    ensure_dirs()
    chunks = _load_chunks()
    build_vector_index(chunks)
    build_fact_store()
    print("\nIndex build complete.")


if __name__ == "__main__":
    run()
