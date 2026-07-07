# Implementation Guide: Mutual Fund FAQ Assistant (Facts-Only RAG)

This is the concrete build plan for the system specified in
[context.md](context.md) and designed in [architecture.md](architecture.md). It
fixes a technology stack, defines the project layout, and gives step-by-step,
file-by-file instructions to implement the two pipelines (ingestion + query),
the guardrails, and the UI.

Scope reminder: **URL-only ingestion** of the 5 Groww pages. No PDF / KIM / SID
parsing. Answers are **≤3 sentences, exactly one citation, with a footer**, and
advisory queries are **refused**.

---

## 1. Technology Stack

| Concern            | Choice | Why |
|--------------------|--------|-----|
| Language           | Python 3.11+ | Best RAG/ML ecosystem |
| Fetcher            | Playwright (Chromium) | Groww is JS-rendered; plain `requests` returns an empty shell |
| HTML parsing       | BeautifulSoup4 + lxml | Selector-based structured extraction |
| Embeddings         | BGE (`BAAI/bge-small-en-v1.5`) via `sentence-transformers` | Strong retrieval quality, local, free; use the `query:`/passage prefix convention |
| Vector store       | Chroma (persistent, local) | Zero-infra, metadata filtering built-in |
| Fact store         | SQLite (`facts.db`) | Deterministic exact lookups for numbers |
| LLM (generate + classify) | Claude (Anthropic API) | Grounded answers + zero-shot intent classification |
| UI                 | Streamlit | Fastest path to the minimal chat UI |
| Config             | `pydantic-settings` + `.env` | API key + paths |
| Tests              | `pytest` | Guardrail + extraction unit tests |

> **LLM model id:** do not hardcode a model id from memory. Before wiring the
> Anthropic client, confirm the current model id and pricing via the `claude-api`
> skill / official reference. Default to a current, capable Claude model.

---

## 2. Project Structure

```
RAG/
├── context.md
├── architecture.md
├── implementation.md
├── README.md
├── requirements.txt
├── .env.example
├── config.py                 # settings: paths, model ids, API key
├── data/
│   ├── raw/                   # rendered HTML snapshots (audit)
│   ├── chroma/                # persisted vector index
│   └── facts.db               # SQLite fact store
├── corpus/
│   └── sources.yaml           # the 5 URLs + scheme_id + category + selectors
├── ingest/
│   ├── __init__.py
│   ├── fetch.py               # Playwright fetcher → raw HTML
│   ├── extract.py             # structured facts + clean prose
│   ├── chunk.py               # prose → chunks + metadata
│   └── build_index.py         # embed + write Chroma + SQLite (entrypoint)
├── app/
│   ├── __init__.py
│   ├── classify.py            # intent classifier (rules + LLM)
│   ├── retrieve.py            # fact-first + vector retrieval, scheme matching
│   ├── generate.py            # grounded answer via Claude
│   ├── guardrails.py          # sentence cap, citation, footer, PII scrub
│   ├── refusal.py             # refusal text + AMFI/SEBI links
│   ├── pipeline.py            # orchestrates query → response
│   └── prompts.py             # system prompts
├── ui/
│   └── streamlit_app.py       # chat UI
├── tests/
│   ├── test_guardrails.py
│   ├── test_classify.py
│   └── test_extract.py
└── .github/
    └── workflows/
        └── ingest.yml         # scheduled daily ingestion (GitHub Actions)
```

---

## 3. Configuration

### `corpus/sources.yaml`
Single source of truth for what gets ingested. Selectors are placeholders —
verify against the live DOM during Phase 1.

```yaml
schemes:
  - scheme_id: hdfc-mid-cap-direct-growth
    name: HDFC Mid-Cap Fund - Direct Growth
    category: Mid Cap
    url: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth
  - scheme_id: nj-flexi-cap-direct-growth
    name: NJ Flexi Cap Fund - Direct Growth
    category: Flexi Cap
    url: https://groww.in/mutual-funds/nj-flexi-cap-fund-direct-growth
  - scheme_id: jm-multi-strategy-direct-growth
    name: JM Multi Strategy Fund - Direct Growth
    category: Multi Strategy
    url: https://groww.in/mutual-funds/jm-multi-strategy-fund-direct-growth
  - scheme_id: jm-midcap-direct-growth
    name: JM Midcap Fund - Direct Growth
    category: Mid Cap
    url: https://groww.in/mutual-funds/jm-midcap-fund-direct-growth
  - scheme_id: lic-mutual-fund-amc
    name: LIC Mutual Fund
    category: AMC Overview
    url: https://groww.in/mutual-funds/amc/lic-mutual-funds

edu_links:                # for refusals only — NOT indexed
  amfi: https://www.amfiindia.com/investor-corner
  sebi: https://investor.sebi.gov.in/
```

### `.env.example`
```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=<confirm-current-claude-model-id>
EMBED_MODEL=BAAI/bge-small-en-v1.5
```

### `requirements.txt`
```
playwright
beautifulsoup4
lxml
sentence-transformers
chromadb
anthropic
streamlit
pydantic-settings
pyyaml
pytest
```
Post-install: `playwright install chromium`.

---

## 4. Build Phases

### Phase 0 — Project setup
1. Create the structure in §2, `python -m venv`, install `requirements.txt`,
   run `playwright install chromium`.
2. Implement `config.py` (load `.env`, expose paths + model ids).
3. Copy `.env.example` → `.env`, add your `ANTHROPIC_API_KEY`.

### Phase 1 — Fetcher (`ingest/fetch.py`)
- For each scheme in `sources.yaml`: open Chromium, `goto(url)`,
  `wait_for_load_state("networkidle")`, wait for a known content selector.
- Save rendered HTML to `data/raw/<scheme_id>.html`; record `fetched_at` (UTC date).
- **Manual step:** open the saved HTML / live page in devtools and capture the real
  CSS selectors for each fact field → fill into an extraction map. Groww renders
  facts in labelled rows; selectors must be confirmed, not assumed.
- Output: raw HTML + a `fetched_at` map.

### Phase 2 — Extractor (`ingest/extract.py`)
- **Structured:** for each known field (expense_ratio, exit_load, min_sip,
  min_lumpsum, aum, riskometer, benchmark, lock_in, fund_house, category), run its
  selector, normalize the value (units `%`/`₹`/`years`, trim), and emit a Fact
  Store record `{scheme_id, scheme_name, category, field, value, source_url, fetched_at}`.
  Missing field → store `null` (never fabricate).
- **Prose:** strip nav/footer/ads, collect visible text blocks → a cleaned document
  string per scheme.
- Add a validation check: if a critical field is `null` across all schemes, log a
  loud warning (selector likely broke).

### Phase 3 — Chunk + Index (`ingest/chunk.py`, `ingest/build_index.py`)

#### Chunking strategy (data-driven)
The Phase 2 output is **not** long free text — it is, per scheme, ~19 atomic
key→value facts plus a 1–2 sentence description (the AMC page: 12 facts + a
schemes-offered list). So sliding-window/token chunking is the wrong tool: there
is nothing long to split, and windowing would glue unrelated facts together,
blur which fact a citation supports, and hurt retrieval precision. We instead use
**structured, fact-aligned chunking** — one retrievable unit per fact — sized by
*meaning*, not tokens.

**Chunk types** (all share metadata: `chunk_id`, `chunk_type`, `scheme_id`,
`scheme_name`, `category`, `field`/`field_tags`, `source_url`, `fetched_at`):

1. **Atomic fact chunks (primary).** One chunk per non-null `(scheme, field)`,
   rendered as a self-contained natural-language sentence that names the scheme so
   it embeds well and reads correctly in isolation:
   - `expense_ratio` → "The expense ratio of HDFC Mid-Cap Fund (Direct Growth) is 0.75%."
   - `exit_load` → "The exit load of NJ Flexi Cap Fund (Direct Growth) is Nil."
   - `riskometer` → "The riskometer (risk level) of JM Midcap Fund (Direct Growth) is Very High."
   This 1 fact = 1 chunk mapping is what makes the **exactly-one-citation** rule
   clean: the retrieved chunk's `source_url` is the citation, and its `value`
   matches the SQLite fact store exactly.

2. **Query-affinity phrasing.** Each fact chunk's text appends the common **user
   synonyms** for that field so BGE retrieves it regardless of wording (kept in a
   `FIELD_SYNONYMS` map, e.g. `expense_ratio` → "annual charges, TER, fund fees";
   `min_sip` → "minimum SIP, smallest SIP instalment"; `exit_load` → "redemption
   charge, exit penalty"). Synonyms live in the embedded text, not the displayed
   answer.

3. **Per-scheme summary chunk (one per scheme).** A single chunk concatenating all
   that scheme's facts (`"HDFC Mid-Cap Fund (Direct Growth): category Mid Cap;
   expense ratio 0.75%; exit load 1% if redeemed within 1 year; benchmark NIFTY
   Midcap 150 TRI; riskometer Very High; …"`). Serves broad/multi-fact queries
   ("tell me about HDFC Mid-Cap") and acts as a recall backstop; still maps to one
   `source_url`.

4. **Prose chunk (0–1 per scheme).** The scheme's own `description` as a single
   chunk (it is short — no splitting). Skipped when empty.

5. **AMC chunks (LIC page).** Atomic fact chunks for the 12 AMC facts, plus **one
   `schemes_offered` chunk** listing the fund names (already short; keep whole, do
   not window). `field_tags` distinguish AMC-level fields from scheme-level ones.

**Rules.**
- No fixed token window and **no overlap** — chunks are whole facts, so overlap
  adds nothing and risks duplicate hits.
- A safety cap (e.g. 512 tokens) only ever triggers on the summary/prose chunk;
  if hit, truncate cleanly on a fact boundary, never mid-number.
- Null facts are **not** chunked (no "not available" sentences in the index) — the
  query layer reports missing fields from the fact store, so absent facts stay
  absent from retrieval (consistent with edgecase R4/E2).
- Deterministic `chunk_id = f"{scheme_id}::{chunk_type}::{field or 'summary'}"`
  so re-ingestion **upserts** instead of duplicating (edgecase C4).

#### Indexing (`build_index.py`, entrypoint `python -m ingest.build_index`)
- Read `data/extracted/*.json`; build the chunk list per the strategy above.
- Embed chunk **passages plainly** with `EMBED_MODEL` (BGE); the BGE search
  **instruction prefix is applied to the query only**, at query time — never to
  stored passages (edgecase C2). Normalize embeddings; cosine similarity.
- Persist into Chroma at `data/chroma/`, upserting by `chunk_id`; store the embed
  model id in collection metadata so a query-time mismatch is detectable (C3).
- Write all fact records into SQLite `data/facts.db`
  (`facts(scheme_id, field, value, source_url, fetched_at)`, PK `(scheme_id, field)`,
  `INSERT OR REPLACE`), so numeric lookups stay deterministic and the index +
  DB are written as one run (C5/C7).

### Phase 4 — Query pipeline (`app/`)
Implement in this order; `pipeline.py` wires them together.

1. **`classify.py`** — `classify(query) -> "FACTUAL" | "ADVISORY" | "OUT_OF_SCOPE"`.
   - Fast path: regex/keyword rules for advisory phrases
     (`should i`, `which is better`, `recommend`, `worth it`, `will it (go|grow|rise)`,
     `best fund`). Match → `ADVISORY`.
   - Else call Claude zero-shot with a strict 1-word-label prompt. Bias to refusal
     on low confidence.
2. **`retrieve.py`** — retrieval strategy is **data-driven** off the Phase 3
   artifacts: every fact is *both* an atomic chunk in Chroma *and* a keyed row in
   `facts.db`, so the cheapest correct path is deterministic fact-first, with
   vector search only as the recall fallback. Pipeline:

   1. **`resolve_scheme(query) -> scheme_id | None | AMBIGUOUS`.** Match the query
      against scheme names + a hand-built **alias map** (the corpus has two Mid-Cap
      funds and an AMC page, so matching must disambiguate):
      - `hdfc-mid-cap-direct-growth` ← "hdfc", "hdfc midcap/mid cap"
      - `jm-midcap-direct-growth` ← "jm midcap/mid cap"
      - `jm-multi-strategy-direct-growth` ← "jm flexicap/flexi cap/multi strategy"
      - `nj-flexi-cap-direct-growth` ← "nj", "nj flexi cap"
      - `lic-mutual-fund-amc` ← "lic", "lic mutual fund" (AMC-level page)
      Bare "midcap" with no AMC token → AMBIGUOUS (HDFC vs JM); bare "JM" with no
      sub-type → AMBIGUOUS (JM Midcap vs JM Flexicap). Return `None` if no scheme.
   2. **`detect_field(query) -> field | None`.** Reverse-index the **same
      `FIELD_SYNONYMS`/`FIELD_LABELS` maps used at chunk time** (import them from
      `ingest.chunk`, do not re-spell synonyms — they must stay in lockstep with
      what was embedded) so query wording → canonical field. Covers fields that
      live only in `facts.db` and were *not* chunked (e.g. `isin`, `nav_date`).
   3. **Fact-first (`lookup_fact(scheme_id, field)`).** If both scheme and field
      resolve, do an exact `SELECT value, source_url, fetched_at FROM facts WHERE
      scheme_id=? AND field=?`. A non-null hit is the answer; its `source_url` is
      the citation and `value` is authoritative (numbers never go through the LLM).
      A row that is present-but-null, or no row, → "not available in sources"
      (edgecase R4/E2) — do **not** fall through to vector search to invent one.
   4. **Vector fallback (`vector_search(query, scheme_id, k=4)`).** For
      multi-fact/broad queries, or when `detect_field` is `None`, embed the query
      **with the BGE prefix from the collection metadata** (`Represent this
      sentence for searching relevant passages: `) — never embed it plainly, and
      never re-prefix the stored passages (edgecase C2/C3: verify the collection's
      `embed_model` matches `settings.embed_model` first). Filter Chroma by
      `where={"scheme_id": scheme_id}` when known so a fact can't leak across the
      two midcap funds; otherwise query unfiltered. Use each chunk's `display`
      (synonym-free) document for grounding, and `summary`/`prose` chunks as the
      recall backstop.
   5. **Evidence bundle** `{scheme_id, facts:[{field,value}], chunks:[{display,
      source_url}], source_url, fetched_at}`. `source_url`/`fetched_at` come from
      the fact row or the single best chunk — all of a scheme's chunks share one
      `source_url`, which keeps the **exactly-one-citation** rule trivially true.
3. **`generate.py`** — call Claude with `prompts.SYSTEM_GROUNDED` + the evidence.
   - Rules in prompt: answer only from context; if absent → "not available in
     sources"; ≤3 sentences; no advice/comparison/projection.
   - Return `{answer_text, source_url}`.
4. **`guardrails.py`** — `enforce(answer_text, source_url, fetched_at)`:
   - Split sentences; if >3, keep first 3 (or regenerate once).
   - Ensure exactly one `source_url` and that it is in the corpus allowlist.
   - PII scrub: regex for PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (12 digits),
     email, phone, long account numbers → strip/redact in I/O, never log.
   - Advisory-leak check: re-scan output for recommendation language → if found,
     replace with refusal.
   - Append footer `Last updated from sources: <fetched_at>`.
5. **`refusal.py`** — `refuse(reason)` returns polite text reinforcing facts-only +
   one `edu_link` (AMFI for general, SEBI for investor-protection) + footer.
6. **`pipeline.py`** — `answer(query)`:
   ```
   intent = classify(query)
   if intent != FACTUAL: return refuse(intent)
   scheme = resolve_scheme(query)
   if scheme is None/ambiguous: return clarify()  # or best-match
   evidence = retrieve(query, scheme)
   draft = generate(evidence)
   return guardrails.enforce(draft, evidence.source_url, evidence.fetched_at)
   ```

### Phase 5 — UI (`ui/streamlit_app.py`)
- Header + disclaimer banner: **"Facts-only. No investment advice."**
- Three clickable example questions (from architecture §5).
- `st.chat_input` → `pipeline.answer()` → render answer, citation link, footer.
- No login, no PII input fields, no user-identity persistence.
- Run: `streamlit run ui/streamlit_app.py`.

### Phase 6 — Tests + README
- `tests/test_guardrails.py`: >3 sentences truncated; footer appended; PII redacted;
  advisory text → refusal.
- `tests/test_classify.py`: advisory queries → `ADVISORY`; factual → `FACTUAL`.
- `tests/test_extract.py`: extractor returns normalized values on a saved HTML fixture.
- `README.md`: setup, selected schemes, RAG architecture overview, known limitations,
  disclaimer snippet (per context.md deliverables).

### Phase 7 — Scheduler (`.github/workflows/ingest.yml`) — *implemented*

**Goal:** run the ingestion pipeline automatically once a day so `facts.db` and the
Chroma index carry fresh Groww data without a manual `python -m ingest.build_index`.
Implemented as a **GitHub Actions scheduled workflow** (built later — this section is
the spec).

**Trigger.**
- `schedule: cron` — one daily run (e.g. `0 1 * * *`, ~06:30 IST; note GitHub cron is
  **UTC** and best-effort, so it may start a few minutes late).
- `workflow_dispatch` — a manual "Run now" button for re-ingesting on selector drift
  or ad-hoc refreshes.

**Job outline (single Ubuntu runner).**
1. `actions/checkout`.
2. `actions/setup-python` (3.11) with pip cache.
3. `pip install -r requirements.txt` then `playwright install --with-deps chromium`
   (Linux needs `--with-deps` for the browser system libraries).
4. Provide `ANTHROPIC_API_KEY` from **GitHub Actions secrets** (`${{ secrets.* }}`),
   never committed. Note: `build_index` itself does not call Claude, so ingestion can
   run even without the key; keep the secret optional for this job.
5. Run the entrypoint: `python -m ingest.build_index` (which runs fetch → extract →
   chunk → index and writes `data/facts.db` + `data/chroma/`).

**Persisting the refreshed index (decide before building).** The runner is ephemeral,
so the regenerated `data/` must be published somewhere the app can read. Options, in
rough order of simplicity:
- **Commit back to the repo** — add/commit `data/facts.db`, `data/chroma/`, and
  `data/raw/` on a bot commit (`git add data && git commit && git push`). Simplest if
  the app is redeployed from the repo; downside is binary churn in git history.
- **Upload as a build artifact / release asset** — `actions/upload-artifact`; the
  deploy step (or the app host) pulls the latest artifact. Keeps git clean.
- **Push to external storage** (S3/GCS/etc.) that the running app mounts or syncs.
  Best if the Streamlit app is hosted separately from the repo.

**Resilience & guardrails for the job.**
- **Fetch failures:** Playwright/network flakiness or Groww selector drift can make a
  field `null` (Phase 2 already logs a loud warning). The workflow should **fail
  visibly** (non-zero exit) if a critical field is null across all schemes, so a broken
  selector surfaces as a red run instead of silently shipping empty facts. Consider a
  step that greps the run log for the Phase 2 warning and fails the job.
- **Idempotency:** re-ingestion **upserts** by `chunk_id` / `INSERT OR REPLACE`
  (Phase 3, edgecase C4/C5), so a daily run cleanly overwrites — no duplicate chunks.
- **Freshness:** `fetched_at` is refreshed each run and flows into the answer footer
  automatically (§6), so the daily run keeps "Last updated from sources" current.
- **Notifications:** rely on GitHub's failed-workflow email, or add a notify step.

**Secrets & safety.** Only `ANTHROPIC_API_KEY` (if used) lives in Actions secrets;
no PII is fetched or logged by ingestion. Restrict the workflow to the default branch.

---

## 5. Prompts (`app/prompts.py`)

**Grounded answer (system):**
```
You answer factual questions about specific mutual fund schemes using ONLY the
provided CONTEXT. Rules:
- Use only facts in CONTEXT. If the answer is not present, say it is not available
  in the sources.
- Maximum 3 sentences. Plain, factual tone.
- No investment advice, recommendations, comparisons, or future projections.
- Do not invent numbers. Do not add a citation or footer (the app adds those).
```

**Intent classifier (system):**
```
Classify the user query into exactly one label: FACTUAL, ADVISORY, or OUT_OF_SCOPE.
- FACTUAL: asks for a verifiable fact about a mutual fund scheme (expense ratio,
  exit load, min SIP, riskometer, benchmark, lock-in, category, fund house).
- ADVISORY: asks for an opinion, recommendation, comparison, or prediction.
- OUT_OF_SCOPE: unrelated to the supported mutual fund schemes.
Reply with the label only.
```

---

## 6. Operational Notes

- **Re-ingestion:** rerun `python -m ingest.build_index` to refresh facts; the
  `fetched_at` date flows into the footer automatically.
- **Selector drift:** if extraction warnings fire, re-capture selectors (Phase 1
  manual step) — this is the most likely maintenance task (architecture §9).
- **Determinism for numbers:** always prefer `lookup_fact` over the LLM for numeric
  fields; the LLM is a phrasing layer, not a calculator.
- **Secrets:** `.env` only; never commit the API key; never log query PII.

---

## 7. Definition of Done (maps to Success Criteria)

- [ ] All 5 Groww pages fetched + indexed; `facts.db` populated, Chroma persisted.
- [ ] Factual queries return ≤3 sentences, exactly one valid corpus citation, footer.
- [ ] Advisory/out-of-scope queries are politely refused with an AMFI/SEBI link.
- [ ] No PII is stored or echoed.
- [ ] UI shows welcome, 3 examples, and the facts-only disclaimer.
- [ ] Tests pass; README documents setup, schemes, architecture, limitations.
```
