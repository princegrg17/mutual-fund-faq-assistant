"""Inspect the chunk embeddings stored in the Chroma vector index.

Reads the `mf_chunks` collection built by `ingest.build_index` and prints, for
each chunk, its id, text, and embedding (dimension + a preview of the vector).

Run:
    python view_embeddings.py                # summary + first few chunks
    python view_embeddings.py --full         # print the entire vector
    python view_embeddings.py --limit 3      # only the first 3 chunks
    python view_embeddings.py --id <chunk_id>  # one specific chunk
"""
from __future__ import annotations

import argparse
import sys

import chromadb

from config import CHROMA_DIR

# Windows consoles default to cp1252, which can't encode symbols like ₹ — force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

COLLECTION_NAME = "mf_chunks"
PREVIEW = 8  # how many vector components to show when not --full


def main() -> None:
    ap = argparse.ArgumentParser(description="View chunk embeddings from Chroma.")
    ap.add_argument("--limit", type=int, default=5, help="max chunks to show")
    ap.add_argument("--full", action="store_true", help="print the whole vector")
    ap.add_argument("--id", dest="chunk_id", help="show only this chunk_id")
    args = ap.parse_args()

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    print(f"Collection : {COLLECTION_NAME}")
    print(f"Vectors    : {collection.count()}")
    print(f"Metadata   : {collection.metadata}")
    print("-" * 70)

    if args.chunk_id:
        res = collection.get(ids=[args.chunk_id], include=["embeddings", "documents"])
    else:
        res = collection.get(
            limit=args.limit, include=["embeddings", "documents"]
        )

    ids = res["ids"]
    embeddings = res["embeddings"]
    documents = res["documents"]

    if len(ids) == 0:
        print("No chunks found.")
        return

    for cid, emb, doc in zip(ids, embeddings, documents):
        vec = list(emb)
        print(f"id   : {cid}")
        print(f"dim  : {len(vec)}")
        print(f"text : {doc}")
        if args.full:
            print(f"embed: {vec}")
        else:
            preview = ", ".join(f"{v:+.4f}" for v in vec[:PREVIEW])
            print(f"embed: [{preview}, ...] (use --full to see all)")
        print("-" * 70)


if __name__ == "__main__":
    main()
