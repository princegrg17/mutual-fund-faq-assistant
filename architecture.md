# Architecture: Mutual Fund FAQ Assistant (Facts-Only RAG)

This document describes the technical architecture for the facts-only mutual fund
FAQ assistant defined in [context.md](context.md) and
[Problem statement.tx](Problem%20statement.tx). The system answers **objective,
verifiable** questions about a fixed set of Groww mutual fund pages, returns **≤3
sentences with exactly one citation**, and **refuses** advisory queries.

Guiding principle: **accuracy over intelligence.** When in doubt, the system
refuses or returns "not found in sources" rather than guessing.

---

## 1. High-Level Overview

The system has two pipelines:

- **Ingestion (offline / batch):** Fetch the 5 Groww URLs → extract facts → chunk →
  embed → store in a vector index + a structured fact store.
- **Query (online / per request):** Classify intent → (refuse | retrieve) → ground
  answer in retrieved chunks → enforce format → return answer + single citation.

```
                          ┌──────────────────────────────────────────────┐
   INGESTION (offline)    │                                              │
                          ▼                                              │
  ┌─────────┐   ┌───────────────┐   ┌──────────────┐   ┌──────────────┐ │
  │ 5 Groww │──▶│  Fetcher      │──▶│  Extractor / │──▶│  Chunker +   │ │
  │  URLs   │   │ (headless     │   │  Normalizer  │   │  Metadata    │ │
  └─────────┘   │  browser)     │   └──────────────┘   └──────┬───────┘ │
                └───────────────┘                            │         │
                                                             ▼         │
                                            ┌────────────────────────┐ │
                                            │  Embedding model       │ │
                                            └───────────┬────────────┘ │
                                                        ▼              │
                              ┌──────────────────┐  ┌──────────────────┐
                              │  Fact Store      │  │  Vector Index    │
                              │  (structured     │  │  (chunks +       │
                              │   key→value)     │  │   metadata)      │
                              └────────┬─────────┘  └────────┬─────────┘
   ─────────────────────────────────── │ ──────────────────  │ ──────────
   QUERY (online)                      │                     │
                                       ▼                     ▼
  ┌────────┐   ┌────────────┐   ┌────────────────────────────────┐
  │  User  │──▶│  Intent    │──▶│  Retriever (vector + fact      │
  │ query  │   │ Classifier │   │  lookup)                       │
  └────────┘   └─────┬──────┘   └───────────────┬────────────────┘
                     │ advisory                 │ factual
                     ▼                          ▼
              ┌─────────────┐         ┌──────────────────────┐
              │  Refusal    │         │  Answer Generator     │
              │  Handler    │         │  (grounded LLM, ≤3    │
              │ (+edu link) │         │   sentences)          │
              └──────┬──────┘         └──────────┬───────────┘
                     │                           ▼
                     │                ┌──────────────────────┐
                     │                │  Format/Guardrail     │
                     │                │  Validator (1 cite,   │
                     │                │  footer, sentence cap)│
                     └────────┬───────┴──────────┬───────────┘
                              ▼                  ▼
                         ┌──────────────────────────┐
                         │   Response to UI          │
                         └──────────────────────────┘
```

---

## 2. Source Corpus

Fixed corpus of 5 Groww pages (from [context.md](context.md)):

| # | Scheme / Page          | Category            | URL |
|---|------------------------|---------------------|-----|
| 1 | HDFC Mid-Cap Fund      | Mid-cap             | groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 2 | NJ Flexi Cap Fund      | Flexi-cap           | groww.in/mutual-funds/nj-flexi-cap-fund-direct-growth |
| 3 | JM Multi Strategy Fund | Multi/dynamic       | groww.in/mutual-funds/jm-multi-strategy-fund-direct-growth |
| 4 | JM Midcap Fund         | Mid-cap             | groww.in/mutual-funds/jm-midcap-fund-direct-growth |
| 5 | LIC Mutual Fund        | AMC overview        | groww.in/mutual-funds/amc/lic-mutual-funds |

**Key constraint:** Groww pages are **JavaScript-rendered** — a plain HTTP `GET`
returns a near-empty HTML shell. Ingestion **must** use a headless browser (or an
internal data API) to obtain rendered content. This is the single biggest
technical risk and is addressed in §3.1.

AMFI / SEBI links are **not** part of the indexed corpus — they are a static lookup
table used only for refusal/educational links.

---

## 3. Ingestion Pipeline (Offline)

Run as a scheduled/batch job (e.g., daily or on-demand). Produces two artifacts
consumed by the query pipeline: the **Vector Index** and the **Fact Store**.

### 3.1 Fetcher
- **Tool:** Headless browser — Playwright (recommended) or Selenium.
- Loads each URL, waits for network idle / key selectors to render, captures the
  fully rendered DOM (and optionally a snapshot HTML file for auditability).
- Records `fetched_at` timestamp per page → feeds the `Last updated from sources`
  footer.
- Polite crawling: low concurrency, retries with backoff, respect robots/ToS.
- Stores raw rendered HTML in `data/raw/<scheme-id>.html` for reproducibility.

### 3.2 Extractor / Normalizer
Two complementary extraction strategies run on the rendered DOM:

1. **Structured extraction (deterministic):** CSS/XPath selectors target the
   labelled fact blocks Groww renders (Expense ratio, Exit load, Min SIP, Min
   lumpsum, Fund size/AUM, Category, Riskometer, Benchmark, Lock-in, Fund house).
   Output → normalized key→value records in the **Fact Store**. This path is the
   primary source of truth for numeric facts (avoids LLM hallucination on numbers).
2. **Prose extraction (for semantic search):** Clean visible text (strip nav,
   ads, footers) → passages used for embedding/retrieval.

Normalization rules:
- Canonicalize units (`%`, `₹`, "years"), trim whitespace, standardize field names.
- Attach provenance: `{source_url, scheme_id, field, value, fetched_at}`.
- Flag missing fields explicitly as `null` (never invent values).

### 3.3 Chunker + Metadata
- Chunk prose into ~200–400 token passages with small overlap.
- Each chunk carries metadata: `scheme_id`, `scheme_name`, `category`,
  `source_url`, `fetched_at`, `field_tags[]`.
- Keep chunks small and field-tagged so retrieval maps cleanly to a single citation.

### 3.4 Embedding + Storage
- **Embedding model:** **BGE** (`BAAI/bge-small-en-v1.5`); the same model must be
  used at ingest and query time. Use BGE's asymmetric convention — store chunks as
  plain passages and prefix queries with the BGE search instruction; normalize
  embeddings and retrieve by cosine similarity.
- **Vector Index:** FAISS / Chroma (local, simple) — stores chunk vectors +
  metadata. Suitable given the tiny corpus (5 pages).
- **Fact Store:** lightweight JSON / SQLite keyed by `(scheme_id, field)` for exact
  deterministic lookups of numeric facts.

---

## 4. Query Pipeline (Online)

### 4.1 Intent Classifier (Refusal Gate)
First stage on every request. Classifies the query into:
- **FACTUAL** — asks for a verifiable fact present in scope (expense ratio, exit
  load, min SIP, riskometer, benchmark, lock-in, category, statement-download
  process). → proceed to retrieval.
- **ADVISORY / OPINION** — "Should I invest?", "Which is better?", return
  predictions, comparisons of performance. → route to Refusal Handler.
- **OUT-OF-SCOPE** — unrelated to the 5 schemes / mutual funds. → polite refusal.

Implementation: rules/keyword heuristics for high-precision advisory phrases
("should I", "which is better", "recommend", "will it go up") **plus** an LLM
zero-shot classifier fallback. Bias toward refusal when uncertain.

### 4.2 Retriever
For FACTUAL queries:
- **Fact-first lookup:** if the query maps to a known field + scheme, read the
  value directly from the **Fact Store** (deterministic, exact). This is preferred
  for numeric facts.
- **Vector retrieval:** embed query → top-k similar chunks from the Vector Index,
  filtered by `scheme_id` when the scheme is identified.
- Resolve the target scheme via name matching (handles "HDFC midcap", "JM midcap"
  disambiguation). If ambiguous across schemes, ask a brief clarifying question or
  return the best-matched single scheme citation.

### 4.3 Answer Generator (Grounded LLM)
- Input: retrieved fact(s)/chunk(s) + their single best `source_url`.
- A modern, capable LLM generates a concise answer **strictly grounded** in the
  retrieved context (no outside knowledge). System prompt enforces:
  - Use only provided context; if the fact is absent, say it's not available in
    the sources.
  - Maximum **3 sentences**.
  - No advice, no comparison, no projections.
- The citation is the `source_url` of the chunk/fact actually used.

### 4.4 Format / Guardrail Validator
Deterministic post-processing before the response leaves the system:
- **Sentence cap:** truncate/regenerate if > 3 sentences.
- **Exactly one citation:** ensure a single valid `source_url` from the corpus.
- **Footer:** append `Last updated from sources: <fetched_at date>`.
- **Privacy scrub:** reject/strip any PAN, Aadhaar, account number, OTP, email, or
  phone in input or output (never store them).
- **Advisory leak check:** final regex/LLM check that no recommendation language
  slipped through; if it did, replace with refusal.

### 4.5 Refusal Handler
For ADVISORY / OUT-OF-SCOPE:
- Returns a polite, clearly worded refusal that reinforces the facts-only limit.
- Includes one relevant educational link from the **AMFI/SEBI lookup table**.
- Same footer/format rules apply.

---

## 5. User Interface (Minimal)

Single-page chat UI (e.g., Streamlit / simple web app):
- **Welcome message** + visible disclaimer banner: **"Facts-only. No investment advice."**
- **Three example questions**, e.g.:
  - "What is the expense ratio of HDFC Mid-Cap Fund?"
  - "What is the exit load of JM Midcap Fund?"
  - "What is the minimum SIP for NJ Flexi Cap Fund?"
- Chat input → renders answer, citation link, and footer.
- No login, no PII fields, no persistence of user identity.

---

## 6. Component & Technology Summary

| Layer            | Responsibility                          | Suggested Tech |
|------------------|------------------------------------------|----------------|
| Fetcher          | Render JS pages, snapshot HTML           | Playwright |
| Extractor        | Structured facts + clean prose           | BeautifulSoup / selectors |
| Embeddings       | Vectorize chunks & queries               | BGE (`BAAI/bge-small-en-v1.5`) |
| Vector Index     | Semantic retrieval                       | FAISS / Chroma |
| Fact Store       | Deterministic numeric lookups            | SQLite / JSON |
| Classifier       | Refusal gate                             | Rules + LLM zero-shot |
| Generator        | Grounded ≤3-sentence answers             | Capable LLM (grounded) |
| Guardrails       | Format, citation, footer, privacy        | Deterministic code |
| UI               | Chat, disclaimer, examples               | Streamlit / web |

> LLM selection: prefer a current, capable model for the generator/classifier and
> verify model IDs and pricing against the official Claude API reference before
> wiring it in (see the `claude-api` skill) rather than hardcoding from memory.

---

## 7. Data Model (Sketch)

**Fact Store record**
```json
{
  "scheme_id": "hdfc-mid-cap-direct-growth",
  "scheme_name": "HDFC Mid-Cap Fund - Direct Growth",
  "category": "Mid Cap",
  "field": "expense_ratio",
  "value": "0.74%",
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "fetched_at": "2026-06-28"
}
```

**Vector chunk metadata**
```json
{
  "chunk_id": "hdfc-mid-cap-direct-growth#0007",
  "scheme_id": "hdfc-mid-cap-direct-growth",
  "category": "Mid Cap",
  "field_tags": ["exit_load"],
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "fetched_at": "2026-06-28",
  "text": "Exit load: 1% if redeemed within 1 year ..."
}
```

---

## 8. Compliance & Privacy Controls

- **No PII processing:** PAN, Aadhaar, account numbers, OTPs, emails, phone numbers
  are never collected, logged, or stored (enforced in §4.4).
- **No advice:** content restrictions enforced at classifier + generator + final
  validator (defense in depth).
- **No performance math:** return/comparison queries are refused or redirected to
  the official factsheet link only.
- **Traceability:** every fact carries `source_url` + `fetched_at`; raw HTML
  snapshots retained for audit.

---

## 9. Known Limitations & Risks

- **JS-rendered source:** Groww layout/selectors can change; structured extraction
  needs monitoring and may break silently → add extraction validation checks.
- **Freshness:** facts are only as current as the last ingestion run; the footer
  date communicates this. Live values (NAV, AUM) may drift between runs.
- **Aggregator source:** Groww is not the AMC of record; values should ideally be
  cross-checked against the AMC factsheet (out of current scope).
- **Disambiguation:** two mid-cap funds (HDFC, JM) require careful scheme matching.
- **Small corpus:** retrieval quality is high but coverage is limited to indexed
  fields; unknown fields must return "not available in sources," not a guess.

---

## 10. Deliverables Mapping

| Requirement (context.md)        | Where handled |
|---------------------------------|----------------|
| Facts-only ≤3 sentences         | §4.3, §4.4 |
| Exactly one citation            | §4.4 |
| `Last updated from sources` footer | §3.1, §4.4 |
| Refusal + educational link      | §4.1, §4.5 |
| Welcome + 3 examples + disclaimer | §5 |
| No PII                          | §4.4, §8 |
| Official-source-only citations  | §2, §3 |
