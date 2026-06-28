"""Retrieval (Phase 4) — fact-first SQLite + BGE/Chroma vector fallback.

Implements the data-driven strategy from implementation.md §Phase 4.2. Every
fact is both a keyed row in ``facts.db`` and an atomic chunk in Chroma, so we
prefer the deterministic SQLite read and only fall back to vector search for
broad/multi-fact queries or when the field can't be pinned.

Public API:
    resolve_scheme(query) -> str | None | "__AMBIGUOUS__"
    detect_field(query)   -> str | None
    lookup_fact(scheme_id, field) -> dict | None
    vector_search(query, scheme_id, k) -> list[dict]
    retrieve(query, scheme_id) -> dict   # evidence bundle
"""
from __future__ import annotations

import re
import sqlite3
from functools import lru_cache

from config import FACTS_DB, CHROMA_DIR, SCHEMES, settings
# Reuse the SAME maps that built the chunks so query↔passage vocab stays in lockstep.
from ingest.chunk import FIELD_SYNONYMS, FIELD_LABELS

AMBIGUOUS = "__AMBIGUOUS__"
COLLECTION_NAME = "mf_chunks"

# --------------------------------------------------------------------------- #
# Scheme resolution
# --------------------------------------------------------------------------- #
# Ordered alias rules: (compiled regex, scheme_id). First match wins, so put the
# most specific (two-token) patterns before bare ones.
_SCHEME_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhdfc\b", re.I), "hdfc-mid-cap-direct-growth"),
    (re.compile(r"\bjm\b.*\b(midcap|mid[- ]?cap)\b", re.I), "jm-midcap-direct-growth"),
    (re.compile(r"\bjm\b.*\b(flexi[- ]?cap|flexicap|multi[- ]?strategy)\b", re.I),
     "jm-multi-strategy-direct-growth"),
    (re.compile(r"\bnj\b", re.I), "nj-flexi-cap-direct-growth"),
    (re.compile(r"\blic\b", re.I), "lic-mutual-fund-amc"),
]

_VALID_IDS = {s["scheme_id"] for s in SCHEMES}


def resolve_scheme(query: str) -> str | None | str:
    """Return a scheme_id, None (no scheme), or AMBIGUOUS (needs clarification)."""
    matched = [sid for pat, sid in _SCHEME_RULES if pat.search(query)]
    # De-dup while preserving order.
    seen: list[str] = []
    for sid in matched:
        if sid not in seen:
            seen.append(sid)
    if len(seen) == 1:
        return seen[0]
    if len(seen) > 1:
        return AMBIGUOUS

    q = query.lower()
    has_midcap = re.search(r"\bmid[- ]?cap|midcap\b", q)
    has_jm = re.search(r"\bjm\b", q)
    # "midcap" with no house token → HDFC vs JM ambiguity.
    if has_midcap and not has_jm:
        return AMBIGUOUS
    # bare "JM" with no sub-type → JM Midcap vs JM Flexicap ambiguity.
    if has_jm:
        return AMBIGUOUS
    return None


def ambiguous_options(query: str) -> list[str]:
    """Human-readable scheme names for the clarify() prompt."""
    q = query.lower()
    if re.search(r"\bjm\b", q):
        return ["JM Midcap Fund", "JM Multi Strategy (Flexicap) Fund"]
    if re.search(r"mid[- ]?cap|midcap", q):
        return ["HDFC Mid-Cap Fund", "JM Midcap Fund"]
    return [s["name"] for s in SCHEMES]


# --------------------------------------------------------------------------- #
# Field detection (reverse-index the chunk-time maps)
# --------------------------------------------------------------------------- #
def _build_field_index() -> list[tuple[str, str]]:
    """(phrase, field) pairs, longest-phrase-first for greedy matching."""
    pairs: list[tuple[str, str]] = []
    for field, label in FIELD_LABELS.items():
        pairs.append((label.lower(), field))
        pairs.append((field.replace("_", " "), field))
    for field, syn in FIELD_SYNONYMS.items():
        for phrase in syn.split(","):
            phrase = phrase.strip().lower()
            if phrase:
                pairs.append((phrase, field))
    # Longest phrases first so "minimum lumpsum" beats "minimum".
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


_FIELD_INDEX = _build_field_index()


def detect_field(query: str) -> str | None:
    q = " " + query.lower() + " "
    for phrase, field in _FIELD_INDEX:
        if len(phrase) < 3:
            continue
        if re.search(r"\b" + re.escape(phrase) + r"\b", q):
            return field
    return None


# --------------------------------------------------------------------------- #
# Fact-first SQLite read
# --------------------------------------------------------------------------- #
def lookup_fact(scheme_id: str, field: str) -> dict | None:
    """Exact fact-store read. Returns the row dict (value may be None) or None."""
    conn = sqlite3.connect(FACTS_DB)
    try:
        row = conn.execute(
            "SELECT value, source_url, fetched_at FROM facts "
            "WHERE scheme_id=? AND field=?",
            (scheme_id, field),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"field": field, "value": row[0], "source_url": row[1], "fetched_at": row[2]}


def _scheme_meta(scheme_id: str) -> dict:
    """source_url + fetched_at for a scheme (from any of its fact rows)."""
    conn = sqlite3.connect(FACTS_DB)
    try:
        row = conn.execute(
            "SELECT source_url, fetched_at FROM facts WHERE scheme_id=? LIMIT 1",
            (scheme_id,),
        ).fetchone()
    finally:
        conn.close()
    return {"source_url": row[0] if row else None,
            "fetched_at": row[1] if row else None}


# --------------------------------------------------------------------------- #
# Vector fallback (BGE query prefix + Chroma)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embed_model)


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    coll = client.get_collection(COLLECTION_NAME)
    # Edgecase C3: query-time embed model must match the indexed one.
    indexed = (coll.metadata or {}).get("embed_model")
    if indexed and indexed != settings.embed_model:
        raise RuntimeError(
            f"Embed model mismatch: index built with {indexed!r}, "
            f"query using {settings.embed_model!r}. Re-run ingest.build_index."
        )
    return coll


def _query_prefix(coll) -> str:
    return (coll.metadata or {}).get(
        "query_prefix", "Represent this sentence for searching relevant passages: "
    )


def vector_search(query: str, scheme_id: str | None = None, k: int = 4) -> list[dict]:
    coll = _collection()
    text = _query_prefix(coll) + query
    emb = _embedder().encode(
        [text], normalize_embeddings=True, convert_to_numpy=True
    ).tolist()
    where = {"scheme_id": scheme_id} if scheme_id else None
    res = coll.query(query_embeddings=emb, n_results=k, where=where)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "display": doc,
            "source_url": meta.get("source_url"),
            "fetched_at": meta.get("fetched_at"),
            "field": meta.get("field") or None,
            "chunk_type": meta.get("chunk_type"),
            "score": 1.0 - dist if dist is not None else None,
        })
    return out


# --------------------------------------------------------------------------- #
# Orchestration → evidence bundle
# --------------------------------------------------------------------------- #
def retrieve(query: str, scheme_id: str) -> dict:
    """Build the evidence bundle for a FACTUAL query with a resolved scheme."""
    field = detect_field(query)
    facts: list[dict] = []
    chunks: list[dict] = []
    source_url = None
    fetched_at = None

    # 1) Fact-first: deterministic, authoritative for numbers.
    if field:
        row = lookup_fact(scheme_id, field)
        if row is not None:
            source_url = row["source_url"]
            fetched_at = row["fetched_at"]
            if row["value"] is not None:
                facts.append({"field": field, "value": row["value"]})

    # 2) Vector fallback for broad/multi-fact queries, or no resolvable field,
    #    or a field that wasn't in the fact store.
    if not facts:
        chunks = vector_search(query, scheme_id=scheme_id, k=4)
        if chunks:
            source_url = source_url or chunks[0]["source_url"]
            fetched_at = fetched_at or chunks[0]["fetched_at"]

    # All of a scheme's chunks share one source_url; backfill from the store.
    if source_url is None or fetched_at is None:
        meta = _scheme_meta(scheme_id)
        source_url = source_url or meta["source_url"]
        fetched_at = fetched_at or meta["fetched_at"]

    return {
        "scheme_id": scheme_id,
        "field": field,
        "facts": facts,
        "chunks": chunks,
        "source_url": source_url,
        "fetched_at": fetched_at,
    }
