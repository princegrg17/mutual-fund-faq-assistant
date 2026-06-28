"""Grounded answer generation (Phase 4).

Determinism for numbers: when fact-first retrieval returned an exact fact, we
phrase the answer **deterministically** from the fact-store value (the LLM is a
phrasing layer, not a calculator — implementation.md §6). Only broad/multi-fact
queries that fell back to vector chunks go through Claude, grounded strictly in
the supplied CONTEXT. With no API key we fall back to the retrieved chunk text so
the pipeline still answers offline.
"""
from __future__ import annotations

from config import SCHEMES, settings
from ingest.chunk import FIELD_LABELS
from app.prompts import SYSTEM_GROUNDED

NOT_AVAILABLE = "That information is not available in the sources."

_SCHEME_NAMES = {s["scheme_id"]: s["name"] for s in SCHEMES}


def _fact_sentence(scheme_id: str, field: str, value: str) -> str:
    label = FIELD_LABELS.get(field, field.replace("_", " "))
    name = _SCHEME_NAMES.get(scheme_id, "the scheme")
    return f"The {label} of {name} is {value}."


def _context_block(evidence: dict) -> str:
    lines: list[str] = []
    for f in evidence.get("facts", []):
        lines.append(_fact_sentence(evidence["scheme_id"], f["field"], f["value"]))
    for c in evidence.get("chunks", []):
        if c.get("display"):
            lines.append(c["display"])
    return "\n".join(f"- {ln}" for ln in lines)


def _llm_answer(query: str, context: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.anthropic_model or "claude-opus-4-8",
            max_tokens=256,
            system=SYSTEM_GROUNDED,
            messages=[{
                "role": "user",
                "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}",
            }],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception:  # noqa: BLE001 — fall back to deterministic text
        return None


def generate(query: str, evidence: dict) -> dict:
    """Return {answer_text, source_url, fetched_at}."""
    facts = evidence.get("facts", [])
    chunks = evidence.get("chunks", [])

    # Nothing retrieved → honest "not available", still cite the scheme page.
    if not facts and not chunks:
        return {
            "answer_text": NOT_AVAILABLE,
            "source_url": evidence.get("source_url"),
            "fetched_at": evidence.get("fetched_at"),
        }

    # Single exact fact → deterministic phrasing (no LLM, no drift on numbers).
    if len(facts) == 1 and not chunks:
        f = facts[0]
        answer = _fact_sentence(evidence["scheme_id"], f["field"], f["value"])
        return {
            "answer_text": answer,
            "source_url": evidence.get("source_url"),
            "fetched_at": evidence.get("fetched_at"),
        }

    # Broad / multi-fact → grounded LLM phrasing over CONTEXT.
    context = _context_block(evidence)
    answer = _llm_answer(query, context)
    if answer is None:
        # Offline fallback: stitch the top chunk/fact displays (≤3 sentences).
        sentences = [ln.lstrip("- ") for ln in context.splitlines()][:3]
        answer = " ".join(sentences) if sentences else NOT_AVAILABLE
    return {
        "answer_text": answer,
        "source_url": evidence.get("source_url"),
        "fetched_at": evidence.get("fetched_at"),
    }
