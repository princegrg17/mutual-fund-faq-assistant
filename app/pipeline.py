"""Query pipeline (Phase 4) — wires classify → retrieve → generate → guardrails.

    answer(query) -> {answer, citation, footer, refused, ...}

Flow (architecture §4):
    intent = classify(query)
    if intent != FACTUAL:            -> refuse
    scheme = resolve_scheme(query)
    if None:                         -> out-of-scope refusal
    if AMBIGUOUS:                    -> clarify
    evidence = retrieve(query, scheme)
    draft    = generate(query, evidence)
    return guardrails.enforce(...)
"""
from __future__ import annotations

from app import classify as _classify
from app import retrieve as _retrieve
from app import generate as _generate
from app import guardrails, refusal


def answer(query: str) -> dict:
    intent = _classify.classify(query)
    if intent == "ADVISORY":
        return guardrails.enforce_refusal(refusal.refuse("ADVISORY"))
    if intent == "OUT_OF_SCOPE":
        return guardrails.enforce_refusal(refusal.refuse("OUT_OF_SCOPE"))

    # FACTUAL → resolve which scheme the user means.
    scheme = _retrieve.resolve_scheme(query)
    if scheme is None:
        return guardrails.enforce_refusal(refusal.refuse("OUT_OF_SCOPE"))
    if scheme == _retrieve.AMBIGUOUS:
        opts = _retrieve.ambiguous_options(query)
        return guardrails.enforce_refusal(refusal.clarify(opts))

    evidence = _retrieve.retrieve(query, scheme)
    draft = _generate.generate(query, evidence)
    return guardrails.enforce(
        draft["answer_text"], draft["source_url"], draft["fetched_at"]
    )


if __name__ == "__main__":  # quick manual smoke test
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    q = " ".join(sys.argv[1:]) or "What is the expense ratio of HDFC Mid-Cap Fund?"
    r = answer(q)
    print(f"Q: {q}\n")
    print(r["answer"])
    if r.get("citation"):
        print(f"\nSource: {r['citation']}")
    if r.get("edu_link"):
        print(f"Learn more: {r['edu_link']}")
    if r.get("footer"):
        print(r["footer"])
