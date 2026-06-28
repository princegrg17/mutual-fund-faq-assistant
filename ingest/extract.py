"""Phase 2 — Extractor / Normalizer.

Reads the rendered HTML snapshots from Phase 1 and produces:

1. A **Fact Store** (deterministic key->value records) — the source of truth for
   numeric facts (architecture §3.2). Written to ``data/facts.json`` for viewing
   and consumed later by Phase 3 (SQLite + vector index).
2. **Clean prose** per scheme for semantic retrieval.

Groww is a Next.js app: every fact is in the embedded ``__NEXT_DATA__`` JSON
(``mfServerSideData`` for scheme pages, ``amcMainPageData`` for the AMC page).
Parsing JSON is far more robust than CSS selectors and avoids the selector-drift
risk from edgecase.md §2. The one exception is the **riskometer**, whose current
value is shown only in the rendered widget, so we read it from the HTML text.

Normalization rules (edgecase E2/E3/E5):
- Missing or placeholder values (``""``, ``-``, ``NA``) normalize to ``null`` —
  never fabricate.
- Units are explicit (``%``, ``₹``, ``crore``).

Output (human-viewable):
- ``data/facts.json``            — flat list of all fact records.
- ``data/extracted/<id>.json``   — per-scheme facts + prose.

Run:  python -m ingest.extract
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

from config import DATA_DIR, RAW_DIR, SCHEMES, ensure_dirs

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

FACTS_JSON = DATA_DIR / "facts.json"
EXTRACTED_DIR = DATA_DIR / "extracted"
MANIFEST_PATH = RAW_DIR / "manifest.json"

# Only truly empty / dash / NA markers. NOTE: "nil"/"none"/"0" are NOT placeholders
# — for fields like exit_load and lock_in, "Nil"/"None" is a meaningful fact
# (= no exit load / no lock-in), not a missing value (edgecase E2 vs E3).
_PLACEHOLDERS = {"", "-", "--", "na", "n/a", "null"}
_RISK_LEVELS = [
    "Very High", "Moderately High", "Low to Moderate", "Moderate", "High", "Low",
]


# --------------------------------------------------------------------------- #
# Normalization helpers
# --------------------------------------------------------------------------- #
def _clean(value) -> str | None:
    """Trim strings; map placeholders/empties to None (never fabricate)."""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _PLACEHOLDERS:
        return None
    return s


def _pct(value) -> str | None:
    s = _clean(value)
    if s is None:
        return None
    s = s.rstrip("%").strip()
    try:
        num = float(s)
    except ValueError:
        return None
    # Drop trailing zeros: 0.750 -> 0.75, 1.0 -> 1
    return f"{num:g}%"


def _rupees(value) -> str | None:
    s = _clean(value)
    if s is None:
        return None
    try:
        num = float(s)
    except ValueError:
        return f"₹{s}"
    return f"₹{num:,.0f}" if num == int(num) else f"₹{num:,.2f}"


def _crore(value) -> str | None:
    s = _clean(value)
    if s is None:
        return None
    try:
        num = float(s)
    except ValueError:
        return None
    return f"₹{num:,.2f} crore"


def _lock_in(value) -> str | None:
    """lock_in is {'years':.., 'months':.., 'days':..} or None."""
    if not isinstance(value, dict):
        return None
    parts = []
    for unit in ("years", "months", "days"):
        v = value.get(unit)
        if v:
            parts.append(f"{v} {unit}")
    return ", ".join(parts) if parts else "No lock-in"


# --------------------------------------------------------------------------- #
# Snapshot loading
# --------------------------------------------------------------------------- #
def _load_next_data(scheme_id: str) -> tuple[dict, str]:
    path = RAW_DIR / f"{scheme_id}.html"
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        raise RuntimeError(f"{scheme_id}: __NEXT_DATA__ not found in snapshot")
    return json.loads(tag.string), html


def _riskometer_from_html(html: str) -> str | None:
    """Read the current riskometer label from the rendered widget (edgecase E7)."""
    pattern = re.compile(
        r"(" + "|".join(re.escape(l) for l in _RISK_LEVELS) + r")\s+Risk",
        re.IGNORECASE,
    )
    matches = [m.group(1).title() for m in pattern.finditer(html)]
    if not matches:
        return None
    # Most frequent label wins (the scheme's own riskometer).
    return Counter(matches).most_common(1)[0][0]


# --------------------------------------------------------------------------- #
# Per-page extractors
# --------------------------------------------------------------------------- #
def _extract_scheme(scheme: dict, data: dict, html: str) -> tuple[dict, str]:
    """Extract structured facts + prose for a fund scheme page."""
    m = data["props"]["pageProps"]["mfServerSideData"]

    facts: dict[str, str | None] = {
        "scheme_name": _clean(m.get("scheme_name")) or scheme["name"],
        "fund_house": _clean(m.get("fund_house")),
        "fund_category": _clean(m.get("category")),          # e.g. Equity
        "sub_category": _clean(m.get("sub_category")),        # e.g. Mid Cap
        "plan_type": _clean(m.get("plan_type")),
        "expense_ratio": _pct(m.get("expense_ratio")),
        "exit_load": _clean(m.get("exit_load")),
        "benchmark": _clean(m.get("benchmark_name") or m.get("benchmark")),
        "aum": _crore(m.get("aum")),
        "min_sip": _rupees(m.get("min_sip_investment")),
        "min_lumpsum": _rupees(m.get("min_investment_amount")),
        "min_additional": _rupees(m.get("mini_additional_investment")),
        "lock_in": _lock_in(m.get("lock_in")),
        "fund_manager": _clean(m.get("fund_manager")),
        "launch_date": _clean(m.get("launch_date")),
        "nav": _rupees(m.get("nav")),
        "nav_date": _clean(m.get("nav_date")),
        "riskometer": _riskometer_from_html(html),
        "isin": _clean(m.get("isin")),
    }

    # Prose for semantic retrieval: ONLY the scheme's own description. Groww's
    # category_info.definition is unreliable (often mismatched to the wrong
    # category, e.g. a "Contra fund" blurb on a Mid Cap fund), so we exclude it
    # to avoid grounding answers in incorrect text.
    prose = _clean(m.get("description")) or ""
    return facts, prose


def _extract_amc(scheme: dict, data: dict, html: str) -> tuple[dict, str]:
    """Extract AMC-level facts for the LIC AMC overview page."""
    blocks = data["props"]["pageProps"]["amcMainPageData"]
    ki: dict = {}
    schemes_block = None
    for b in blocks:
        if isinstance(b, dict):
            if "key_information" in b and isinstance(b["key_information"], dict):
                ki = b["key_information"]
            if "content" in b and isinstance(b.get("content"), list):
                schemes_block = b

    total_schemes = None
    scheme_names: list[str] = []
    if schemes_block:
        total_schemes = (
            schemes_block.get("total_result")
            or schemes_block.get("total_results")
        )
        scheme_names = [
            n for n in (
                _clean(x.get("scheme_name") or x.get("fund_name"))
                for x in schemes_block["content"]
            ) if n
        ]
        if not total_schemes:
            total_schemes = len(scheme_names)

    facts: dict[str, str | None] = {
        "fund_house": _clean(ki.get("fund_house") or ki.get("asset_management_company")),
        "amc_setup_date": _clean(ki.get("amc_setup_date")),
        "sponsor": _clean(", ".join(ki.get("sponsor_name", [])) or None),
        "trustee": _clean(ki.get("trustee_organisation")),
        "chairman": _clean(ki.get("chairman")),
        "managing_director": _clean(ki.get("md")),
        "ceo": _clean(ki.get("ceo")),
        "cio": _clean(ki.get("cio")),
        "compliance_officer": _clean(ki.get("compliance_officer")),
        "total_aum": _crore(ki.get("total_aum")),
        "address": _clean(ki.get("address")),
        "total_schemes": _clean(total_schemes),
    }
    prose_parts = [_clean(ki.get("address"))]
    if scheme_names:
        prose_parts.append("Schemes offered: " + "; ".join(scheme_names))
    prose = "\n".join(p for p in prose_parts if p)
    return facts, prose


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run() -> dict:
    ensure_dirs()
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.exists() else {}
    )

    all_records: list[dict] = []
    per_scheme: dict[str, dict] = {}
    critical = ("expense_ratio", "exit_load", "benchmark")  # for drift check
    critical_present = {c: 0 for c in critical}

    for scheme in SCHEMES:
        sid = scheme["scheme_id"]
        snap = RAW_DIR / f"{sid}.html"
        if not snap.exists():
            print(f"  [{sid}] SKIP — no snapshot")
            continue

        fetched_at = manifest.get(sid, {}).get("fetched_at")
        data, html = _load_next_data(sid)
        is_amc = "amcMainPageData" in data["props"]["pageProps"]
        facts, prose = (
            _extract_amc(scheme, data, html) if is_amc
            else _extract_scheme(scheme, data, html)
        )

        n_present = sum(1 for v in facts.values() if v is not None)
        print(f"  [{sid}] {n_present}/{len(facts)} fields ({'AMC' if is_amc else 'scheme'})")

        for field, value in facts.items():
            if field in critical_present and value is not None:
                critical_present[field] += 1
            all_records.append({
                "scheme_id": sid,
                "scheme_name": scheme["name"],
                "category": scheme.get("category"),
                "field": field,
                "value": value,
                "source_url": scheme["url"],
                "fetched_at": fetched_at,
            })

        per_scheme[sid] = {
            "scheme_id": sid,
            "scheme_name": scheme["name"],
            "category": scheme.get("category"),
            "source_url": scheme["url"],
            "fetched_at": fetched_at,
            "is_amc_page": is_amc,
            "facts": facts,
            "prose": prose,
        }
        (EXTRACTED_DIR / f"{sid}.json").write_text(
            json.dumps(per_scheme[sid], indent=2, ensure_ascii=False), encoding="utf-8"
        )

    FACTS_JSON.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Drift warning (edgecase E1): a critical field null across ALL scheme pages.
    n_scheme_pages = sum(1 for s in per_scheme.values() if not s["is_amc_page"])
    for field, count in critical_present.items():
        if n_scheme_pages and count == 0:
            print(f"  WARNING: '{field}' is null on all scheme pages — selector/JSON drift?")

    print(f"\nDone: {len(all_records)} fact records → {FACTS_JSON}")
    print(f"Per-scheme files → {EXTRACTED_DIR}")
    return per_scheme


if __name__ == "__main__":
    run()
