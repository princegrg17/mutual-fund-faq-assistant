"""Refusal handler (Phase 4).

Advisory / out-of-scope queries get a polite, facts-only refusal plus one
educational link (AMFI for general, SEBI for investor-protection). The footer is
appended by guardrails.enforce_refusal so format rules stay in one place.
"""
from __future__ import annotations

from config import EDU_LINKS

_AMFI = EDU_LINKS.get("amfi", "https://www.amfiindia.com/investor-corner")
_SEBI = EDU_LINKS.get("sebi", "https://investor.sebi.gov.in/")


def refuse(intent: str) -> dict:
    """Return a refusal payload for an ADVISORY / OUT_OF_SCOPE intent.

    Returns {answer_text, edu_link} — the footer is added by guardrails.
    """
    if intent == "ADVISORY":
        text = (
            "I can only share factual information from the official scheme pages — "
            "I can't give investment advice, recommendations, comparisons, or "
            "predictions. For guidance on choosing or evaluating funds, please use "
            "an authorised educational resource."
        )
        link = _SEBI
    else:  # OUT_OF_SCOPE (and any unknown label)
        text = (
            "I can only answer factual questions about the specific mutual fund "
            "schemes in my sources. That question is outside what I cover."
        )
        link = _AMFI
    return {"answer_text": text, "edu_link": link}


def clarify(options: list[str]) -> dict:
    """Ask the user to disambiguate when a scheme name is ambiguous."""
    names = " or ".join(options) if options else "the scheme"
    return {
        "answer_text": (
            f"Could you clarify which scheme you mean — {names}? "
            "I have more than one matching fund and want to cite the right page."
        ),
        "edu_link": None,
    }
