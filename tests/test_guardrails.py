"""Phase 6 — guardrail unit tests (implementation §4 Phase 6).

Covers the hard output constraints:
- >3 sentences truncated to 3 (decimal-/abbreviation-safe split)
- footer appended
- PII redacted (PAN, Aadhaar, email, phone, account number)
- advisory leak in a "factual" answer → refusal
- citation must be on the corpus allowlist
"""
from __future__ import annotations

from config import CORPUS_URLS
from app import guardrails

GOOD_URL = next(iter(CORPUS_URLS))


def test_caps_to_three_sentences():
    text = "One fact. Two fact. Three fact. Four fact. Five fact."
    out = guardrails.enforce(text, GOOD_URL, "2026-06-28")
    assert out["answer"] == "One fact. Two fact. Three fact."


def test_decimal_not_split_as_sentence():
    # "0.75%" and "Rs." must not count as sentence boundaries.
    text = "The expense ratio is 0.75%. The min SIP is Rs. 500. The exit load is Nil."
    out = guardrails.enforce(text, GOOD_URL, "2026-06-28")
    assert out["answer"] == text  # exactly 3 sentences, unchanged


def test_footer_appended():
    out = guardrails.enforce("The exit load is Nil.", GOOD_URL, "2026-06-28")
    assert out["footer"] == "Last updated from sources: 2026-06-28"


def test_pii_redacted():
    text = (
        "Contact ABCDE1234F at user@example.com or 9876543210, "
        "Aadhaar 1234 5678 9012, account 123456789012345."
    )
    out = guardrails.enforce(text, GOOD_URL, "2026-06-28")
    for leaked in ("ABCDE1234F", "user@example.com", "9876543210",
                   "1234 5678 9012", "123456789012345"):
        assert leaked not in out["answer"]
    assert "redacted" in out["answer"]


def test_advisory_leak_becomes_refusal():
    text = "You should buy this fund, it will beat the market."
    out = guardrails.enforce(text, GOOD_URL, "2026-06-28")
    assert out["refused"] is True
    assert out["citation"] is None


def test_invalid_citation_dropped():
    out = guardrails.enforce("The exit load is Nil.", "https://evil.example/x", "2026-06-28")
    assert out["citation"] is None


def test_valid_citation_kept():
    out = guardrails.enforce("The exit load is Nil.", GOOD_URL, "2026-06-28")
    assert out["citation"] == GOOD_URL
