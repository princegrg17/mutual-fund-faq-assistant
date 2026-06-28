"""Phase 3 (chunking) — turn extracted facts into retrieval chunks.

Implements the data-driven, fact-aligned chunking strategy from implementation.md
§Phase 3. The Phase 2 output is structured atomic facts (~19 per scheme) plus a
short description, so we do NOT window by tokens — we emit **one chunk per fact**
(plus a per-scheme summary and an optional prose chunk). This keeps the
1-fact = 1-chunk = 1-citation mapping clean.

Each chunk has:
- ``chunk_id``    deterministic → re-ingestion upserts, never duplicates (edgecase C4)
- ``chunk_type``  one of: fact | summary | prose | amc_fact | schemes_offered
- ``text``        the embedded passage (fact sentence + query synonyms)
- ``display``     the clean human sentence (no synonyms) for answer grounding
- metadata: scheme_id, scheme_name, category, field, field_tags, source_url, fetched_at

Embeds nothing here (that is build_index.py). Writes ``data/chunks.json`` so the
chunk set is viewable before indexing.

Run:  python -m ingest.chunk
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from config import DATA_DIR

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

EXTRACTED_DIR = DATA_DIR / "extracted"
CHUNKS_JSON = DATA_DIR / "chunks.json"

# Safety cap (characters) — only the summary/prose chunk could approach this.
MAX_CHARS = 2_000

# Human-readable labels for fields (used in the fact sentence).
FIELD_LABELS: dict[str, str] = {
    "scheme_name": "scheme name",
    "fund_house": "fund house",
    "fund_category": "fund category",
    "sub_category": "sub-category",
    "plan_type": "plan type",
    "expense_ratio": "expense ratio",
    "exit_load": "exit load",
    "benchmark": "benchmark index",
    "aum": "assets under management (AUM)",
    "min_sip": "minimum SIP amount",
    "min_lumpsum": "minimum lumpsum investment",
    "min_additional": "minimum additional investment",
    "lock_in": "lock-in period",
    "fund_manager": "fund manager",
    "launch_date": "launch date",
    "nav": "NAV (net asset value)",
    "nav_date": "NAV date",
    "riskometer": "riskometer (risk level)",
    "isin": "ISIN",
    # AMC-level
    "amc_setup_date": "AMC setup date",
    "sponsor": "sponsor",
    "trustee": "trustee organisation",
    "chairman": "chairman",
    "managing_director": "managing director",
    "ceo": "CEO",
    "cio": "CIO",
    "compliance_officer": "compliance officer",
    "total_aum": "total assets under management (AUM)",
    "address": "registered address",
    "total_schemes": "number of schemes offered",
}

# User synonyms appended to the embedded text (NOT shown in answers) so BGE
# retrieves the right fact regardless of how the user phrases the question.
FIELD_SYNONYMS: dict[str, str] = {
    "expense_ratio": "annual charges, TER, total expense ratio, fund fees, cost",
    "exit_load": "redemption charge, exit penalty, early withdrawal fee",
    "benchmark": "benchmark, index it tracks, compared against",
    "aum": "fund size, assets managed, corpus",
    "min_sip": "minimum SIP, smallest SIP instalment, start SIP amount",
    "min_lumpsum": "minimum one-time investment, lumpsum, minimum investment amount",
    "min_additional": "additional purchase, top-up minimum",
    "lock_in": "lock in, lock-in, holding period restriction",
    "fund_manager": "manager, who manages the fund",
    "launch_date": "inception date, started, launched",
    "nav": "net asset value, unit price, current NAV",
    "riskometer": "risk level, risk rating, how risky",
    "sub_category": "fund type, category",
    "fund_house": "AMC, asset management company",
    "total_schemes": "how many funds, number of schemes",
    "total_aum": "total fund size, total assets",
    "sponsor": "sponsored by, parent",
}

# Fields excluded from atomic fact chunks (kept in summary only) to avoid noise.
SKIP_FACT_FIELDS = {"scheme_name", "isin", "nav_date", "plan_type", "fund_category"}


def _fact_sentence(scheme_name: str, field: str, value: str) -> str:
    label = FIELD_LABELS.get(field, field.replace("_", " "))
    return f"The {label} of {scheme_name} is {value}."


def _amc_sentence(scheme_name: str, field: str, value: str) -> str:
    label = FIELD_LABELS.get(field, field.replace("_", " "))
    return f"The {label} of {scheme_name} is {value}."


def _with_synonyms(sentence: str, field: str) -> str:
    syn = FIELD_SYNONYMS.get(field)
    return f"{sentence} ({syn})" if syn else sentence


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    # Truncate on a fact boundary (';' or '. '), never mid-value.
    cut = text.rfind(";", 0, MAX_CHARS)
    if cut == -1:
        cut = text.rfind(". ", 0, MAX_CHARS)
    return (text[:cut] if cut != -1 else text[:MAX_CHARS]).rstrip() + " …"


def _meta(rec: dict, field: str | None, field_tags: list[str]) -> dict:
    return {
        "scheme_id": rec["scheme_id"],
        "scheme_name": rec["scheme_name"],
        "category": rec.get("category"),
        "field": field,
        "field_tags": field_tags,
        "source_url": rec["source_url"],
        "fetched_at": rec.get("fetched_at"),
    }


def _chunk(rec: dict, chunk_type: str, field: str | None, text: str,
           display: str, field_tags: list[str]) -> dict:
    cid = f"{rec['scheme_id']}::{chunk_type}::{field or 'summary'}"
    return {
        "chunk_id": cid,
        "chunk_type": chunk_type,
        "text": _truncate(text),
        "display": display,
        **_meta(rec, field, field_tags),
    }


def build_chunks_for_scheme(rec: dict) -> list[dict]:
    """Build all chunks for one extracted scheme/AMC record."""
    chunks: list[dict] = []
    facts: dict = rec["facts"]
    name = facts.get("scheme_name") or rec["scheme_name"]
    is_amc = rec.get("is_amc_page", False)

    # 1) Atomic fact chunks (one per non-null field).
    summary_parts: list[str] = []
    for field, value in facts.items():
        if value is None:
            continue  # null facts are never chunked (edgecase R4/E2)
        label = FIELD_LABELS.get(field, field.replace("_", " "))
        summary_parts.append(f"{label} {value}")
        if field in SKIP_FACT_FIELDS:
            continue
        sentence = (_amc_sentence if is_amc else _fact_sentence)(name, field, value)
        tags = [field] + (["amc"] if is_amc else ["scheme"])
        chunks.append(_chunk(
            rec,
            chunk_type="amc_fact" if is_amc else "fact",
            field=field,
            text=_with_synonyms(sentence, field),
            display=sentence,
            field_tags=tags,
        ))

    # 2) Per-scheme / per-AMC summary chunk.
    summary = f"{name}: " + "; ".join(summary_parts) + "."
    chunks.append(_chunk(
        rec,
        chunk_type="summary",
        field=None,
        text=summary,
        display=summary,
        field_tags=["summary", "amc" if is_amc else "scheme"],
    ))

    # 3) Prose / schemes-offered chunk (if any).
    prose = (rec.get("prose") or "").strip()
    if prose:
        ctype = "schemes_offered" if is_amc else "prose"
        chunks.append(_chunk(
            rec,
            chunk_type=ctype,
            field=ctype,
            text=f"{name}. {prose}",
            display=prose,
            field_tags=[ctype, "amc" if is_amc else "scheme"],
        ))

    return chunks


def run() -> list[dict]:
    files = sorted(EXTRACTED_DIR.glob("*.json"))
    if not files:
        print(f"No extracted files in {EXTRACTED_DIR} — run `python -m ingest.extract` first.")
        return []

    all_chunks: list[dict] = []
    for fp in files:
        rec = json.loads(Path(fp).read_text(encoding="utf-8"))
        sc = build_chunks_for_scheme(rec)
        all_chunks.extend(sc)
        by_type: dict[str, int] = {}
        for c in sc:
            by_type[c["chunk_type"]] = by_type.get(c["chunk_type"], 0) + 1
        print(f"  [{rec['scheme_id']}] {len(sc)} chunks {by_type}")

    # Sanity: chunk_ids must be unique (deterministic upsert key, edgecase C4).
    ids = [c["chunk_id"] for c in all_chunks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"  WARNING: duplicate chunk_ids: {dupes}")

    CHUNKS_JSON.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nDone: {len(all_chunks)} chunks → {CHUNKS_JSON}")
    return all_chunks


if __name__ == "__main__":
    run()
