"""Phase 1 — Fetcher.

Groww scheme pages are JavaScript-rendered, so a plain HTTP GET returns an empty
shell (architecture §2/§3.1). This module drives a headless Chromium browser
(Playwright) to load each curated URL, waits for real content to render, and
writes the fully-rendered HTML to ``data/raw/<scheme_id>.html`` plus a manifest
recording the ``fetched_at`` date that later feeds the answer footer.

Robustness (see edgecase.md §1):
- F2/F3: wait for a content marker, not just ``load``; bounded timeout.
- F3/F4/F6: on failure, keep the previous good snapshot (never overwrite with an
  empty/interstitial page).
- F5/F7: retry with backoff; detect bot-wall/interstitial via missing content.
- F8: scroll to trigger lazy-loaded widgets before snapshotting.

Run:  python -m ingest.fetch
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from config import RAW_DIR, SCHEMES, ensure_dirs

# Windows consoles default to cp1252 and choke on non-ASCII; force UTF-8 so log
# output (URLs, arrows) never crashes the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

MANIFEST_PATH = RAW_DIR / "manifest.json"

# Tuning
NAV_TIMEOUT_MS = 45_000          # per-navigation cap
CONTENT_TIMEOUT_MS = 30_000      # wait for a content marker to appear
MAX_RETRIES = 3
BACKOFF_BASE_S = 3               # 3s, 6s, 12s ...
MIN_RENDERED_CHARS = 5_000       # below this we assume a shell/interstitial

# A scheme page renders fund facts; the AMC page renders a fund list. We wait for
# the page <h1>/main content as a generic "rendered" marker, then validate size.
CONTENT_MARKER = "h1"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_manifest(manifest: dict) -> None:
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(MANIFEST_PATH)  # atomic on same filesystem


def _atomic_write_html(path: Path, html: str) -> None:
    tmp = path.with_suffix(".html.tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(path)


def _render_once(page, url: str) -> str:
    """Navigate and return rendered HTML, or raise on failure/interstitial."""
    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    # Best-effort network settle; ignore if it never idles (F2).
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeoutError:
        pass
    # Wait for a real content marker (F3).
    page.wait_for_selector(CONTENT_MARKER, timeout=CONTENT_TIMEOUT_MS)
    # Trigger lazy-loaded widgets (F8).
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1_500)
    page.evaluate("window.scrollTo(0, 0)")
    html = page.content()
    if len(html) < MIN_RENDERED_CHARS:
        raise RuntimeError(
            f"rendered page too small ({len(html)} chars) — likely a shell or "
            f"interstitial/bot-wall"
        )
    return html


def fetch_scheme(page, scheme: dict) -> dict:
    """Fetch one scheme with retries. Returns a manifest entry dict."""
    scheme_id = scheme["scheme_id"]
    url = scheme["url"]
    out_path = RAW_DIR / f"{scheme_id}.html"

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [{scheme_id}] attempt {attempt}/{MAX_RETRIES} → {url}")
            html = _render_once(page, url)
            _atomic_write_html(out_path, html)
            print(f"  [{scheme_id}] OK ({len(html):,} chars) → {out_path.name}")
            return {
                "scheme_id": scheme_id,
                "url": url,
                "status": "ok",
                "fetched_at": _utc_today(),
                "chars": len(html),
                "html_file": out_path.name,
            }
        except (PWTimeoutError, RuntimeError, Exception) as err:  # noqa: BLE001
            last_err = err
            print(f"  [{scheme_id}] attempt {attempt} failed: {err}")
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** (attempt - 1))
                print(f"  [{scheme_id}] backing off {delay}s ...")
                time.sleep(delay)

    # All retries failed — keep any previous good snapshot (F3/F4/F6).
    kept = out_path.exists()
    print(
        f"  [{scheme_id}] FAILED after {MAX_RETRIES} attempts; "
        f"{'kept previous snapshot' if kept else 'no prior snapshot'}"
    )
    return {
        "scheme_id": scheme_id,
        "url": url,
        "status": "failed",
        "error": str(last_err),
        "kept_previous_snapshot": kept,
        "fetched_at": None,
    }


def run() -> dict:
    """Fetch all schemes. Returns the updated manifest."""
    ensure_dirs()
    manifest = _load_manifest()

    print(f"Fetching {len(SCHEMES)} Groww pages → {RAW_DIR}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="en-IN")
        page = context.new_page()
        page.set_default_timeout(CONTENT_TIMEOUT_MS)

        for scheme in SCHEMES:
            entry = fetch_scheme(page, scheme)
            # Preserve last good fetched_at if this run failed but a snapshot exists.
            if entry["status"] == "failed" and entry.get("kept_previous_snapshot"):
                prev = manifest.get(scheme["scheme_id"], {})
                if prev.get("fetched_at"):
                    entry["fetched_at"] = prev["fetched_at"]
                    entry["note"] = "using previous snapshot/fetched_at"
            manifest[scheme["scheme_id"]] = entry

        context.close()
        browser.close()

    _save_manifest(manifest)

    ok = sum(1 for e in manifest.values() if e.get("status") == "ok")
    failed = [sid for sid, e in manifest.items() if e.get("status") != "ok"]
    print(f"\nDone: {ok}/{len(SCHEMES)} ok. Manifest → {MANIFEST_PATH}")
    if failed:
        print(f"Failed/stale: {failed}")
    return manifest


if __name__ == "__main__":
    result = run()
    # Non-zero exit if nothing usable was fetched at all (CI signal).
    usable = any(
        (RAW_DIR / f"{s['scheme_id']}.html").exists() for s in SCHEMES
    )
    sys.exit(0 if usable else 1)
