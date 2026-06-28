"""Guardrails (Phase 4) — deterministic post-processing before a response leaves.

Enforces the hard constraints from architecture §4.4 / eval §3.5:
- sentence cap (≤3), robust to "0.75%" / "Rs." / "Pvt. Ltd."
- exactly one citation, from the corpus allowlist
- PII scrub (PAN, Aadhaar, email, phone, long account numbers)
- advisory-leak rescan → replace with refusal
- footer: "Last updated from sources: <fetched_at>"
"""
from __future__ import annotations

import re

from config import CORPUS_URLS
from app import refusal

# --- PII patterns (scrub in/out, never log) --------------------------------- #
_PII = [
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN redacted]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[Aadhaar redacted]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email redacted]"),
    (re.compile(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b"), "[phone redacted]"),
    (re.compile(r"\b\d{11,18}\b"), "[account number redacted]"),
]

# Advisory language that must never appear in a factual answer.
_ADVISORY_LEAK = re.compile(
    r"\b(i recommend|you should|we recommend|is a good (buy|investment|choice)|"
    r"better than|outperform|will (grow|rise|fall|beat)|worth investing|"
    r"i suggest|advisable|go for it)\b",
    re.IGNORECASE,
)

# Sentence splitter that tolerates decimals/abbreviations.
_ABBREV = re.compile(r"(\d)\.(\d)|(\b(?:Rs|Pvt|Ltd|Co|Mr|Ms|No|U\.S|vs)\.)", re.I)


def scrub_pii(text: str) -> str:
    if not text:
        return text
    for pat, repl in _PII:
        text = pat.sub(repl, text)
    return text


def _split_sentences(text: str) -> list[str]:
    # Mask decimals/abbreviation dots so they don't trigger a split.
    masked = _ABBREV.sub(lambda m: m.group(0).replace(".", "\0"), text)
    parts = re.split(r"(?<=[.!?])\s+", masked.strip())
    return [p.replace("\0", ".").strip() for p in parts if p.strip()]


def _cap_sentences(text: str, n: int = 3) -> str:
    sents = _split_sentences(text)
    return " ".join(sents[:n]) if len(sents) > n else text.strip()


def _valid_citation(source_url: str | None) -> str | None:
    return source_url if source_url in CORPUS_URLS else None


def enforce(answer_text: str, source_url: str | None, fetched_at: str | None) -> dict:
    """Final guard for a FACTUAL answer. Returns the response payload."""
    answer = scrub_pii(answer_text or "")

    # Advisory leak → replace whole answer with a refusal (safety-critical).
    if _ADVISORY_LEAK.search(answer):
        return enforce_refusal(refusal.refuse("ADVISORY"), fetched_at)

    answer = _cap_sentences(answer, 3)
    citation = _valid_citation(source_url)
    footer = f"Last updated from sources: {fetched_at}" if fetched_at else \
        "Last updated from sources: unknown"

    return {
        "answer": answer,
        "citation": citation,        # may be None if no valid corpus URL
        "footer": footer,
        "refused": False,
    }


def enforce_refusal(payload: dict, fetched_at: str | None = None) -> dict:
    """Format a refusal/clarify payload: scrub, append edu link + footer."""
    answer = scrub_pii(payload.get("answer_text", ""))
    link = payload.get("edu_link")
    footer = f"Last updated from sources: {fetched_at}" if fetched_at else None
    return {
        "answer": answer,
        "citation": None,            # refusals carry NO corpus citation
        "edu_link": link,
        "footer": footer,
        "refused": True,
    }
