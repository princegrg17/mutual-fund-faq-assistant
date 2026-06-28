"""Intent classifier (Phase 4).

`classify(query) -> "FACTUAL" | "ADVISORY" | "OUT_OF_SCOPE"`.

Two stages, biased toward refusal on uncertainty (compliance-first):
1. High-precision regex rules for advisory phrasing — match → ADVISORY immediately.
2. Otherwise a zero-shot Claude call with a strict 1-word-label prompt.

If no API key is configured the LLM stage is skipped and we fall back to a
conservative keyword heuristic so the pipeline still runs offline/in tests.
"""
from __future__ import annotations

import re

from config import settings
from app.prompts import SYSTEM_CLASSIFY

LABELS = {"FACTUAL", "ADVISORY", "OUT_OF_SCOPE"}

# High-precision advisory phrases. Any match → ADVISORY (safety-critical recall).
_ADVISORY_PATTERNS = [
    r"\bshould i\b",
    r"\bwhich (is|one) (is )?better\b",
    r"\bwhich (fund|scheme|one) should\b",
    r"\brecommend\b",
    r"\bworth (it|investing|buying)\b",
    r"\bis it good\b",
    r"\bwill it (go|grow|rise|fall|drop|give|return)\b",
    r"\bbest\b.{0,20}\b(fund|scheme|investment|option|amc|midcap|mid cap|flexi ?cap)\b",
    r"\bgood (investment|buy|fund|choice)\b",
    r"\bshould (i|we|one) (buy|invest|sell|hold)\b",
    r"\bvs\.?\b|\bversus\b|\bor better\b",
    r"\bwill .* (outperform|beat)\b",
    r"\bhow much (will|can) i (earn|make|gain)\b",
]
_ADVISORY_RE = re.compile("|".join(_ADVISORY_PATTERNS), re.IGNORECASE)

# Factual cues (used only by the offline heuristic fallback): field words, AMC
# roles, and scheme tokens. A named scheme makes "tell me about HDFC" factual.
_FACTUAL_CUES = re.compile(
    r"expense ratio|exit load|min(imum)? sip|lock[- ]?in|riskometer|risk level|"
    r"benchmark|fund house|fund manager|category|nav|aum|launch|sponsor|trustee|"
    r"\bter\b|charges|min(imum)? (lumpsum|investment)|ceo|cio|chairman|"
    r"managing director|compliance|setup date|how many (funds|schemes)|"
    r"\bhdfc\b|\bjm\b|\bnj\b|\blic\b|mid[- ]?cap|midcap|flexi[- ]?cap|flexicap",
    re.IGNORECASE,
)


def _rules(query: str) -> str | None:
    if _ADVISORY_RE.search(query):
        return "ADVISORY"
    return None


def _heuristic(query: str) -> str:
    """Offline fallback when no LLM is available."""
    return "FACTUAL" if _FACTUAL_CUES.search(query) else "OUT_OF_SCOPE"


def _llm(query: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.anthropic_model or "claude-opus-4-8",
            max_tokens=8,
            system=SYSTEM_CLASSIFY,
            messages=[{"role": "user", "content": query}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip().upper()
        for label in LABELS:
            if label in text:
                return label
    except Exception:  # noqa: BLE001 — never let classification crash the pipeline
        return None
    return None


def classify(query: str) -> str:
    rule = _rules(query)
    if rule:
        return rule
    label = _llm(query)
    if label:
        return label
    return _heuristic(query)
