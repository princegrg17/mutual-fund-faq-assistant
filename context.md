# Project Context: Mutual Fund FAQ Assistant (Facts-Only Q&A)

## Summary
A lightweight **Retrieval-Augmented Generation (RAG)** assistant that answers
**objective, verifiable** questions about mutual fund schemes, using **Groww** as
the reference product source. Every answer is drawn **exclusively from the curated
Groww scheme pages listed below** (with AMFI/SEBI used for educational/refusal
links), is short, and is backed by a single citation. The system **never** gives
investment advice, opinions, or recommendations. The guiding principle is
**accuracy over intelligence**.

## Source URLs (Corpus)
The corpus is built from the following Groww pages:

1. HDFC Mid-Cap Fund — Direct Growth: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth
2. NJ Flexi Cap Fund — Direct Growth: https://groww.in/mutual-funds/nj-flexi-cap-fund-direct-growth
3. JM Multi Strategy Fund — Direct Growth: https://groww.in/mutual-funds/jm-multi-strategy-fund-direct-growth
4. JM Midcap Fund — Direct Growth: https://groww.in/mutual-funds/jm-midcap-fund-direct-growth
5. LIC Mutual Fund (AMC page): https://groww.in/mutual-funds/amc/lic-mutual-funds

## Objective
Build a RAG assistant that:
- Answers factual queries about mutual fund schemes.
- Uses a curated corpus of official documents.
- Provides concise, source-backed responses.

## Target Users
- Retail investors comparing mutual fund schemes.
- Customer support / content teams handling repetitive mutual fund queries.

## Scope of Work

### 1. Corpus Definition
- Source: **Groww** mutual fund scheme pages (see **Source URLs** above).
- **5 curated URLs** spanning multiple AMCs and categories:
  - **HDFC Mid-Cap Fund** (Direct Growth) — mid-cap
  - **NJ Flexi Cap Fund** (Direct Growth) — flexi-cap
  - **JM Multi Strategy Fund** (Direct Growth) — multi/dynamic strategy
  - **JM Midcap Fund** (Direct Growth) — mid-cap
  - **LIC Mutual Fund** — AMC overview page
- Each Groww scheme page supplies the facts to be indexed: expense ratio, exit
  load, minimum SIP/lumpsum, riskometer, benchmark, fund category, lock-in (if any),
  and fund house details.
- AMFI / SEBI pages are reserved for educational links used in refusals.

### 2. FAQ Assistant Requirements
Answer **facts-only** queries such as:
- Expense ratio of a scheme
- Exit load details
- Minimum SIP amount
- ELSS lock-in period
- Riskometer classification
- Benchmark index
- Process to download statements / capital gains reports

**Response format rules (hard constraints):**
- Maximum **3 sentences** per response.
- Exactly **one citation link** per response.
- Footer on every answer: `Last updated from sources: <date>`

### 3. Refusal Handling
Refuse non-factual / advisory queries, e.g. "Should I invest in this fund?",
"Which fund is better?". Refusals must:
- Be polite and clearly worded.
- Reinforce the facts-only limitation.
- Provide a relevant educational link (e.g., AMFI or SEBI).

### 4. User Interface (Minimal)
- A welcome message.
- Three example questions.
- A visible disclaimer: **"Facts-only. No investment advice."**

## Constraints

### Data & Sources
- Use **only** the curated **Groww** scheme pages listed in **Source URLs**, plus
  AMFI / SEBI for educational/refusal links.
- **No** third-party blogs or other aggregator websites beyond the designated Groww pages.

### Privacy & Security
Do **not** collect, store, or process:
- PAN or Aadhaar numbers
- Account numbers
- OTPs
- Email addresses or phone numbers

### Content Restrictions
- No investment advice or recommendations.
- No performance comparisons or return calculations.
- For performance-related queries, link to the official factsheet only.

### Transparency
- Responses must be short, factual, and verifiable.
- Every answer must include a source link and last-updated date.

## Expected Deliverables
- **README** with:
  - Setup instructions
  - Selected AMC and schemes
  - Architecture overview (RAG approach)
  - Known limitations
- **Disclaimer snippet:** "Facts-only. No investment advice."

## Success Criteria
- Accurate retrieval of factual mutual fund information.
- Strict adherence to facts-only responses.
- Consistent inclusion of valid source citations.
- Proper refusal of advisory queries.
- Clean, minimal, user-friendly interface.
