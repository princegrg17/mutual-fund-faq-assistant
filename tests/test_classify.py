"""Phase 6 — intent classifier tests (implementation §4 Phase 6).

The LLM stage is disabled (empty API key) so these run offline and
deterministically: advisory phrasing is caught by the regex rules, and the
remaining queries fall through to the keyword heuristic.
"""
from __future__ import annotations

import pytest

from app import classify


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Force the offline path so no network/LLM call is made."""
    monkeypatch.setattr(classify.settings, "anthropic_api_key", "", raising=False)


ADVISORY = [
    "Should I invest in HDFC Mid-Cap Fund?",
    "Which is better, JM Midcap or NJ Flexi Cap?",
    "Is HDFC Mid-Cap a good investment?",
    "Will it grow next year?",
    "What is the best mid cap fund?",
    "Can you recommend a fund?",
]

FACTUAL = [
    "What is the expense ratio of HDFC Mid-Cap Fund?",
    "What is the exit load of JM Midcap Fund?",
    "What is the minimum SIP for NJ Flexi Cap Fund?",
    "Who is the fund manager of NJ Flexi Cap Fund?",
    "What is the benchmark of HDFC Mid-Cap Fund?",
]

OUT_OF_SCOPE = [
    "What is the weather in Mumbai today?",
    "How do I cook biryani?",
]


@pytest.mark.parametrize("q", ADVISORY)
def test_advisory(q):
    assert classify.classify(q) == "ADVISORY"


@pytest.mark.parametrize("q", FACTUAL)
def test_factual(q):
    assert classify.classify(q) == "FACTUAL"


@pytest.mark.parametrize("q", OUT_OF_SCOPE)
def test_out_of_scope(q):
    assert classify.classify(q) == "OUT_OF_SCOPE"
