# Mutual Fund FAQ Assistant (Facts-Only RAG)

A grounded question-answering assistant for a small, curated set of Indian mutual
fund scheme pages. It answers **only verifiable facts** drawn from official source
pages — expense ratio, exit load, minimum SIP, riskometer, benchmark, lock-in,
fund house, and similar — in **≤3 sentences with exactly one citation and a
"last updated" footer**. Advisory, comparison, prediction, and out-of-scope
questions are politely **refused** with a link to an authorised educational
resource (AMFI / SEBI).

> **Facts-only. No investment advice.**

**🔗 Live demo:** https://mutual-fund-faq-assistant-prince.streamlit.app/

---

## Selected schemes (corpus)

The corpus is URL-only ingestion of 5 Groww pages (see [corpus/sources.yaml](corpus/sources.yaml)):

| Scheme | Category | Source |
|--------|----------|--------|
| HDFC Mid-Cap Fund — Direct Growth | Mid Cap | groww.in |
| NJ Flexi Cap Fund — Direct Growth | Flexi Cap | groww.in |
| JM Multi Strategy Fund — Direct Growth | Multi Strategy | groww.in |
| JM Midcap Fund — Direct Growth | Mid Cap | groww.in |
| LIC Mutual Fund | AMC Overview | groww.in |

---

## Architecture overview

Two pipelines (full design in [architecture.md](architecture.md) and
[implementation.md](implementation.md)):

**Ingestion** (`ingest/`) — run once / on refresh:
```
fetch (Playwright) → extract (Next.js JSON → facts + prose)
  → chunk (fact-aligned, 1 fact = 1 chunk) → build_index (Chroma + SQLite)
```

**Query** (`app/`) — per request, orchestrated by `pipeline.answer()`:
```
classify (FACTUAL / ADVISORY / OUT_OF_SCOPE)
  → resolve_scheme (alias map, disambiguates the two Mid-Cap funds)
  → retrieve (fact-first SQLite lookup, vector fallback in Chroma)
  → generate (Claude, grounded on evidence only)
  → guardrails (≤3 sentences, one corpus citation, PII scrub, footer)
```

Key design choices:
- **Fact-first, deterministic numbers.** Every fact is both a keyed row in
  `data/facts.db` and an atomic chunk in Chroma; numeric answers come from the
  exact SQLite lookup, never invented by the LLM.
- **Fact-aligned chunking.** One retrievable unit per fact, so the
  exactly-one-citation rule is trivially satisfied — the chunk's `source_url`
  *is* the citation.
- **BGE embeddings** (`BAAI/bge-small-en-v1.5`), local and free; the search
  instruction prefix is applied to the **query only**, never to stored passages.
- **Compliance-first guardrails** run on every response leaving the system.

Tech stack: Python 3.11+, Playwright, BeautifulSoup4, sentence-transformers (BGE),
Chroma, SQLite, Anthropic Claude, Streamlit, pytest.

---

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  Unix: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env          # then add your ANTHROPIC_API_KEY
```

`.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-8
EMBED_MODEL=BAAI/bge-small-en-v1.5
```

### Build the index (ingestion)

```bash
python -m ingest.fetch          # render + snapshot the 5 pages → data/raw/
python -m ingest.extract        # structured facts + prose → data/extracted/
python -m ingest.build_index    # embed → Chroma + facts.db
```

> Re-ingestion is idempotent: chunks/facts upsert by deterministic id, and the
> `fetched_at` date flows automatically into the answer footer.

### Run the app

```bash
streamlit run ui/streamlit_app.py     # → http://localhost:8501
```

The UI shows a welcome header, the facts-only disclaimer, three clickable example
questions, and a chat box that renders the answer, citation link, and footer.

### Run the tests

```bash
python -m pytest -q
```

Covers guardrails (sentence cap, footer, PII scrub, advisory leak, citation
allowlist), the intent classifier, and extractor normalization against a saved
HTML fixture.

---

## Example questions

- "What is the expense ratio of HDFC Mid-Cap Fund?"
- "What is the exit load of JM Midcap Fund?"
- "What is the minimum SIP for NJ Flexi Cap Fund?"

Advisory questions (e.g. *"Should I invest in HDFC Mid-Cap?"*, *"Which fund is
better?"*) are refused with an AMFI/SEBI link.

---

## Known limitations

- **URL-only ingestion** of 5 Groww pages. No PDF / KIM / SID parsing; coverage is
  limited to the facts those pages expose.
- **Selector / source drift** is the most likely maintenance task — if Groww
  changes its page data shape, extraction warnings fire and selectors/JSON paths
  must be re-captured (re-run `ingest.fetch` + `ingest.extract`).
- **Point-in-time facts.** Values (NAV, AUM, expense ratio) are as of the last
  ingestion `fetched_at`, shown in the footer — not live.
- **No advice, by design.** The system will not compare funds, rank them, or
  project returns, even when asked directly.
- Requires an `ANTHROPIC_API_KEY` for the generation/classification LLM calls;
  classification falls back to an offline heuristic if the key is absent.

---

## Disclaimer

> **Facts-only. No investment advice.** This assistant provides factual
> information sourced from official scheme pages and does not offer investment
> advice, recommendations, comparisons, or predictions. For guidance on choosing
> or evaluating funds, consult an authorised resource such as
> [AMFI](https://www.amfiindia.com/investor-corner) or
> [SEBI](https://investor.sebi.gov.in/).
