"""Phase 5 — premium chat UI (Streamlit), styled after the Stitch "Luminous
Glassmorphism" / Groww design in stitch_groww_mf_faq_assistant/.

Run:  streamlit run ui/streamlit_app.py

Visual language (see stitch_groww_mf_faq_assistant/DESIGN.md):
- Mint/cyan mesh-gradient background, frosted glass cards (backdrop-blur).
- Groww green #00d09c as the high-intent accent (send button, user bubble).
- Inter type, generous whitespace, hairline borders, soft glow over hard shadows.

Content stays facts-only compliant: the three example chips and the disclaimer
are the real, non-advisory questions (the Stitch mock's advisory examples were
intentionally replaced). Backend wiring (pipeline.answer) is unchanged.
"""
from __future__ import annotations

import html as _html
import os
import sys
from pathlib import Path

import streamlit as st

# Make the project root importable when launched via `streamlit run`.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# --- Streamlit Cloud deploy shims (must run BEFORE importing the pipeline) --- #
# 1) Chroma needs sqlite3 >= 3.35, but Streamlit Community Cloud ships an older
#    system sqlite. Swap in the bundled pysqlite3 when present (no-op locally on
#    Windows/macOS where pysqlite3-binary isn't installed).
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

# 2) Bridge Streamlit secrets → env vars so config.py (pydantic-settings) picks
#    up ANTHROPIC_API_KEY / model ids on Streamlit Cloud (no .env there).
try:
    for _k in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "EMBED_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # noqa: BLE001 — no secrets.toml locally is fine
    pass

from app import pipeline  # noqa: E402


@st.cache_resource(show_spinner="Building the fund index…")
def _bootstrap_index() -> bool:
    """Build the Chroma vector index + facts.db on first run if they are missing.

    The ingested source artifacts (``data/chunks.json`` / ``data/facts.json``)
    are committed to the repo, but the derived index (``data/chroma/`` and
    ``data/facts.db``) is gitignored — so on a fresh deploy (e.g. Streamlit
    Cloud) it does not exist yet. Rebuild it once, deterministically, from the
    committed chunks/facts. No network/Playwright ingestion is involved.
    """
    from config import CHROMA_DIR, FACTS_DB

    if FACTS_DB.exists() and (CHROMA_DIR / "chroma.sqlite3").exists():
        return True
    from ingest import build_index

    build_index.run()
    return True


_bootstrap_index()

EXAMPLES = [
    ("trending_up", "What is the expense ratio of HDFC Mid-Cap Fund?"),
    ("payments", "What is the exit load of JM Midcap Fund?"),
    ("savings", "What is the minimum SIP for NJ Flexi Cap Fund?"),
]

st.set_page_config(
    page_title="MF FAQ Assistant",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------- #
# Global styling — Luminous Glassmorphism (Groww-inspired)
# --------------------------------------------------------------------------- #
# Font imports kept in a SEPARATE call: a block that starts with <link> is an
# HTML "type 6" block that ends at the first blank line, which would otherwise
# truncate the <style> below and leak the rest of the CSS as visible text.
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>'
    '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap" rel="stylesheet"/>',
    unsafe_allow_html=True,
)

# The <style> MUST be the first thing in this block (HTML "type 1": runs until
# </style>, so the blank lines between CSS sections are safe).
st.markdown(
    """<style>
:root{
  --primary:#00d09c; --primary-dark:#00b386; --primary-deep:#006c4f;
  --on-surface:#191c1e; --on-variant:#3c4a43; --line:rgba(0,0,0,.08);
}
html, body, [class*="css"]{ font-family:'Inter',sans-serif !important; }

/* Mesh-gradient luminous background */
.stApp{
  background-color:#ffffff;
  background-image:
    radial-gradient(at 0% 0%, hsla(165,100%,41%,0.10) 0px, transparent 50%),
    radial-gradient(at 100% 0%, hsla(233,100%,66%,0.06) 0px, transparent 50%),
    radial-gradient(at 100% 100%, hsla(165,100%,41%,0.06) 0px, transparent 50%),
    radial-gradient(at 0% 100%, hsla(233,100%,66%,0.10) 0px, transparent 50%);
  background-attachment:fixed;
}
/* Hide Streamlit chrome */
#MainMenu, header[data-testid="stHeader"], footer{ visibility:hidden; height:0; }
.block-container{ padding-top:1.2rem; padding-bottom:7rem; max-width:880px; }

.material-symbols-outlined{
  font-family:'Material Symbols Outlined'; font-weight:400; font-style:normal;
  line-height:1; vertical-align:middle; -webkit-font-feature-settings:'liga';
  font-feature-settings:'liga';
}

/* Glass primitives */
.glass{
  background:rgba(255,255,255,.70); backdrop-filter:blur(16px);
  -webkit-backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,.55);
  box-shadow:0 4px 30px rgba(0,0,0,.05);
}

/* Top brand bar */
.navbar{
  display:flex; align-items:center; justify-content:space-between;
  padding:14px 22px; border-radius:18px; margin-bottom:18px;
}
.brand{ display:flex; align-items:center; gap:12px; }
.brand .logo{
  width:42px; height:42px; border-radius:50%; background:var(--primary);
  display:flex; align-items:center; justify-content:center; color:#fff;
  box-shadow:0 4px 16px rgba(0,208,156,.35);
}
.brand .logo .material-symbols-outlined{ font-size:24px; }
.brand h1{ font-size:21px; font-weight:600; color:var(--on-surface); margin:0;
  letter-spacing:-.01em; }
.badge{
  display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600;
  color:var(--primary-deep); background:rgba(0,208,156,.12); border:1px solid rgba(0,208,156,.30);
  padding:7px 14px; border-radius:999px; letter-spacing:.01em;
}
.badge .material-symbols-outlined{ font-size:16px; }

/* Hero */
.hero{ text-align:center; max-width:560px; margin:26px auto 8px; }
.hero .bot{
  width:64px; height:64px; border-radius:50%; background:rgba(0,208,156,.16);
  color:var(--primary); display:flex; align-items:center; justify-content:center;
  margin:0 auto 18px;
}
.hero .bot .material-symbols-outlined{ font-size:32px; }
.hero h2{ font-size:34px; font-weight:700; letter-spacing:-.02em; color:var(--on-surface); margin:0 0 12px; }
.hero p{ font-size:17px; color:var(--on-variant); margin:0; line-height:1.6; }

/* Chat bubbles */
.row{ display:flex; margin:10px 0; }
.row.user{ justify-content:flex-end; }
.row.ai{ justify-content:flex-start; gap:12px; }
.bubble-user{
  max-width:78%; background:var(--primary); color:#fff;
  border-radius:18px 18px 4px 18px; padding:14px 20px; font-size:15px;
  line-height:1.55; box-shadow:0 4px 16px rgba(0,208,156,.22);
}
.ai .avatar{
  width:34px; height:34px; border-radius:50%; background:rgba(0,208,156,.16);
  color:var(--primary); display:flex; align-items:center; justify-content:center;
  flex-shrink:0; align-self:flex-end;
}
.ai .avatar .material-symbols-outlined{ font-size:18px; }
.bubble-ai{
  max-width:82%; background:rgba(255,255,255,.72); backdrop-filter:blur(16px);
  -webkit-backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,.6);
  border-radius:18px 18px 18px 4px; padding:18px 22px; font-size:15px;
  line-height:1.6; color:var(--on-surface); box-shadow:0 4px 30px rgba(0,0,0,.05);
}
.bubble-ai.refusal{ border:1px solid rgba(255,184,0,.45); background:rgba(255,250,235,.85); }

/* Source citation card + footer */
.src{ margin-top:16px; padding-top:14px; border-top:1px solid var(--line); }
.src .label{ font-size:10px; font-weight:700; letter-spacing:.12em; color:var(--on-variant);
  text-transform:uppercase; display:block; margin-bottom:9px; }
.src a{
  display:inline-flex; align-items:center; gap:8px; text-decoration:none;
  background:rgba(255,255,255,.85); border:1px solid var(--line); border-radius:10px;
  padding:8px 12px; font-size:12.5px; font-weight:500; color:var(--on-variant);
  transition:border-color .2s, box-shadow .2s; max-width:100%;
}
.src a:hover{ border-color:var(--primary); box-shadow:0 2px 10px rgba(0,208,156,.18); }
.src a .ico{ width:18px; height:18px; border-radius:5px; background:rgba(0,208,156,.14);
  color:var(--primary); display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.src a .ico .material-symbols-outlined{ font-size:12px; }
.src a .url{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:520px; color:var(--primary-deep); }
.foot{ margin-top:10px; font-size:11.5px; color:var(--on-variant); opacity:.8; }

/* Example chips → Streamlit buttons */
div[data-testid="stButton"] > button{
  width:100%; background:rgba(255,255,255,.70); backdrop-filter:blur(14px);
  border:1px solid rgba(255,255,255,.6); border-radius:999px; color:var(--on-variant);
  font-size:14px; font-weight:500; padding:12px 18px;
  box-shadow:0 4px 24px rgba(0,0,0,.05); transition:all .25s ease;
}
div[data-testid="stButton"] > button:hover{
  border-color:var(--primary); color:var(--primary-deep);
  box-shadow:0 6px 24px rgba(0,208,156,.22); transform:translateY(-1px);
}
div[data-testid="stButton"] > button:active{ transform:translateY(0); }

/* Chat input → glass pill */
div[data-testid="stChatInput"]{
  background:rgba(255,255,255,.92); border:1px solid rgba(0,208,156,.30);
  border-radius:999px; box-shadow:0 6px 26px rgba(0,0,0,.06); backdrop-filter:blur(16px);
}
div[data-testid="stChatInput"]:focus-within{
  border-color:var(--primary); box-shadow:0 6px 26px rgba(0,208,156,.18);
}
div[data-testid="stChatInput"] textarea{ font-size:15px !important; }
div[data-testid="stChatInput"] button{ background:var(--primary) !important; }
.disclaimer{ text-align:center; font-size:11.5px; color:var(--on-variant); opacity:.7; margin-top:8px; }

/* Loading dots */
.dots span{ display:inline-block; width:7px; height:7px; margin:0 2px; border-radius:50%;
  background:var(--primary); animation:bounce 1.2s infinite ease-in-out both; }
.dots span:nth-child(2){ animation-delay:.16s; }
.dots span:nth-child(3){ animation-delay:.32s; }
@keyframes bounce{ 0%,80%,100%{ transform:scale(.5); opacity:.4; } 40%{ transform:scale(1); opacity:1; } }
</style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def _navbar() -> None:
    st.markdown(
        """
<div class="navbar glass">
  <div class="brand">
    <div class="logo"><span class="material-symbols-outlined">auto_awesome</span></div>
    <h1>MF FAQ Assistant</h1>
  </div>
  <span class="badge"><span class="material-symbols-outlined">verified_user</span>Facts-only · No advice</span>
</div>
        """,
        unsafe_allow_html=True,
    )


def _hero() -> None:
    st.markdown(
        """
<div class="hero">
  <div class="bot"><span class="material-symbols-outlined">smart_toy</span></div>
  <h2>Ask about mutual fund facts</h2>
  <p>Verified facts from official scheme pages — expense ratio, exit load,
     minimum SIP, riskometer and more. No advice, no predictions.</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_user(text: str) -> None:
    st.markdown(
        f'<div class="row user"><div class="bubble-user">{_html.escape(text)}</div></div>',
        unsafe_allow_html=True,
    )


def _render_response(resp: dict) -> None:
    answer = _html.escape(resp.get("answer", "")).replace("\n", "<br>")
    refusal = " refusal" if resp.get("refused") else ""

    parts = [f'<p style="margin:0">{answer}</p>']

    citation = resp.get("citation")
    if citation:
        safe = _html.escape(citation)
        parts.append(
            f'<div class="src"><span class="label">Source</span>'
            f'<a href="{safe}" target="_blank">'
            f'<span class="ico"><span class="material-symbols-outlined">article</span></span>'
            f'<span class="url">{safe}</span></a></div>'
        )

    edu = resp.get("edu_link")
    if edu:
        safe = _html.escape(edu)
        parts.append(
            f'<div class="src"><span class="label">Learn more</span>'
            f'<a href="{safe}" target="_blank">'
            f'<span class="ico"><span class="material-symbols-outlined">school</span></span>'
            f'<span class="url">{safe}</span></a></div>'
        )

    footer = resp.get("footer")
    if footer:
        parts.append(f'<div class="foot">{_html.escape(footer)}</div>')

    st.markdown(
        '<div class="row ai">'
        '<div class="avatar"><span class="material-symbols-outlined">smart_toy</span></div>'
        f'<div class="bubble-ai{refusal}">{"".join(parts)}</div></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
_navbar()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        _render_user(msg["content"])
    else:
        _render_response(msg["payload"])


def _handle(query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})
    _render_user(query)
    placeholder = st.empty()
    placeholder.markdown(
        '<div class="row ai"><div class="avatar">'
        '<span class="material-symbols-outlined">smart_toy</span></div>'
        '<div class="bubble-ai"><div class="dots"><span></span><span></span><span></span></div></div></div>',
        unsafe_allow_html=True,
    )
    resp = pipeline.answer(query)
    placeholder.empty()
    _render_response(resp)
    st.session_state.messages.append({"role": "assistant", "payload": resp})


# Hero + example chips only before the first message
if not st.session_state.messages:
    _hero()
    st.write("")
    cols = st.columns(len(EXAMPLES))
    for col, (_icon, example) in zip(cols, EXAMPLES):
        if col.button(example, key=f"ex_{example}", use_container_width=True):
            _handle(example)
            st.rerun()

# Chat input (Streamlit pins this to the bottom)
if prompt := st.chat_input("Ask a factual question about a scheme…"):
    _handle(prompt)
    st.rerun()

st.markdown(
    '<div class="disclaimer">Facts only. No investment advice. '
    'Values are as of the last source update shown above.</div>',
    unsafe_allow_html=True,
)
