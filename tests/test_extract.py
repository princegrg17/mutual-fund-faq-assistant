"""Phase 6 — extractor / normalizer tests (implementation §4 Phase 6).

Two layers:
1. Pure normalization helpers (units, placeholders → null, never fabricate).
2. End-to-end extraction on a saved HTML fixture (the real Phase 1 snapshot),
   asserting normalized values come back in the expected shape.
"""
from __future__ import annotations

import json
import re

import pytest

from config import RAW_DIR, SCHEMES
from ingest import extract

HDFC = "hdfc-mid-cap-direct-growth"


# --- normalization helpers -------------------------------------------------- #
def test_clean_placeholders_to_none():
    for bad in ("", "-", "--", "NA", "n/a", "null"):
        assert extract._clean(bad) is None
    assert extract._clean("  Mid Cap  ") == "Mid Cap"


def test_pct_normalizes_and_trims_zeros():
    assert extract._pct("0.750") == "0.75%"
    assert extract._pct("1.0") == "1%"
    assert extract._pct("0.75%") == "0.75%"
    assert extract._pct("") is None


def test_rupees_formats_with_symbol():
    assert extract._rupees("500") == "₹500"
    assert extract._rupees("1000.5") == "₹1,000.50"
    assert extract._rupees("") is None


def test_crore_unit_explicit():
    assert extract._crore("1234.5") == "₹1,234.50 crore"
    assert extract._crore("NA") is None


def test_lock_in_no_lockin_is_a_fact():
    assert extract._lock_in({}) == "No lock-in"
    assert extract._lock_in({"years": 3}) == "3 years"
    assert extract._lock_in(None) is None


# --- end-to-end on a saved snapshot ----------------------------------------- #
@pytest.mark.skipif(
    not (RAW_DIR / f"{HDFC}.html").exists(),
    reason="no saved HTML fixture (run ingest.fetch first)",
)
def test_extract_scheme_from_fixture():
    scheme = next(s for s in SCHEMES if s["scheme_id"] == HDFC)
    data, html = extract._load_next_data(HDFC)
    facts, prose = extract._extract_scheme(scheme, data, html)

    # Scheme name always present; never fabricated.
    assert facts["scheme_name"]
    # Expense ratio, if present, is a normalized percentage string.
    if facts["expense_ratio"] is not None:
        assert re.fullmatch(r"[\d.]+%", facts["expense_ratio"])
    # Riskometer, if present, is one of the known labels.
    if facts["riskometer"] is not None:
        assert facts["riskometer"] in extract._RISK_LEVELS
    # Prose is always a string (possibly empty), never None.
    assert isinstance(prose, str)


def test_extracted_json_matches_corpus_urls():
    """Persisted extraction (if present) cites only corpus URLs."""
    path = extract.EXTRACTED_DIR / f"{HDFC}.json"
    if not path.exists():
        pytest.skip("no extracted json yet")
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["source_url"].startswith("https://groww.in/")
