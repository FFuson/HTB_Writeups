"""One-shot scraper Playwright para PortSwigger Web Security Academy.

`/web-security/all-labs` es JS-rendered; el sitemap solo expone ~95 labs.
Esta visita la página con headless Chromium y extrae los 270+ labs
totales con título + difficulty (Apprentice/Practitioner/Expert).

Salida: `data/portswigger_seed.json`. Lo consume luego
`fetch_portswigger.py` como fuente primaria (el sitemap queda como
fallback de sanity-check).

Ejecución: **local manual** cuando PortSwigger añada labs (mensual o
trimestral, no semanal). Playwright requiere Chromium ~200 MB que no
queremos en CI.

    pip install playwright
    playwright install chromium
    python -m scripts.scrape_portswigger_extended
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.config import DATA_DIR

ALL_LABS_URL = "https://portswigger.net/web-security/all-labs"
SEED_FILE = DATA_DIR / "portswigger_seed.json"

# Lab URL pattern, soporta sub-topic opcional:
#   /web-security/<topic>/lab-<slug>
#   /web-security/<topic>/<subtopic>/lab-<slug>
_LAB_URL_RE = re.compile(
    r"^https://portswigger\.net/web-security/"
    r"([a-z-]+)(?:/([a-z-]+))?/lab-([a-z0-9-]+)/?$"
)


def _normalize_difficulty(raw: str) -> str | None:
    raw = (raw or "").strip().upper()
    if raw == "APPRENTICE":
        return "Apprentice"
    if raw == "PRACTITIONER":
        return "Practitioner"
    if raw == "EXPERT":
        return "Expert"
    return None


def scrape() -> list[dict]:
    """Devuelve lista de dicts {url, name, difficulty} desde el DOM
    rendereado de /all-labs."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(ALL_LABS_URL, wait_until="domcontentloaded", timeout=60_000)
            # PortSwigger inyecta labs vía JS unos 2-3s después de DOM ready.
            page.wait_for_timeout(4_000)
            items = page.eval_on_selector_all(
                'a[href*="/lab-"]',
                """
                (els) => els.map(a => {
                    // Buscar ancestor que contenga el badge de difficulty
                    let container = a;
                    for (let i = 0; i < 6; i++) {
                        if (!container.parentElement) break;
                        container = container.parentElement;
                        if (container.querySelector('span[class*="label-light"]')) break;
                    }
                    const diffEl = container.querySelector('span[class*="label-light"]');
                    return {
                        href: a.href,
                        name: (a.innerText || '').trim(),
                        difficulty: diffEl ? diffEl.innerText.trim() : ""
                    };
                })
                """
            )
        finally:
            browser.close()
    return items


def main() -> int:
    print(f"[scrape] Loading {ALL_LABS_URL} (Playwright headless)…")
    raw_items = scrape()
    print(f"[scrape] Raw items: {len(raw_items)}")

    # Dedupe por URL. Cuando hay duplicados, preferimos el que tiene
    # name + difficulty no vacíos.
    by_url: dict[str, dict] = {}
    for r in raw_items:
        url = (r.get("href") or "").rstrip("/")
        if not url or not _LAB_URL_RE.match(url + ("/" if not url.endswith("/") else "")):
            # Re-intento sin trailing slash check
            if not _LAB_URL_RE.match(url):
                continue
        existing = by_url.get(url)
        if existing is None:
            by_url[url] = r
            continue
        score_new = bool(r.get("name")) + bool(r.get("difficulty"))
        score_old = bool(existing.get("name")) + bool(existing.get("difficulty"))
        if score_new > score_old:
            by_url[url] = r

    # Normalizar a schema seed.
    seeds: list[dict] = []
    for url, r in by_url.items():
        m = _LAB_URL_RE.match(url)
        if not m:
            continue
        topic_id = m.group(1)
        slug = m.group(3)
        seeds.append({
            "url": url,
            "name": (r.get("name") or "").strip(),
            "topic_id": topic_id,
            "slug": slug,
            "difficulty": _normalize_difficulty(r.get("difficulty", "")),
        })

    seeds.sort(key=lambda s: (s["topic_id"], s["name"].lower()))

    SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(
        json.dumps(seeds, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[scrape] {len(seeds)} labs únicos · saved to {SEED_FILE}")

    # Stats por topic + difficulty
    by_topic = Counter(s["topic_id"] for s in seeds)
    by_diff = Counter(s.get("difficulty") or "Unknown" for s in seeds)
    print(f"[scrape] Difficulty: {dict(by_diff)}")
    print(f"[scrape] Por topic ({len(by_topic)} topics):")
    for t, n in by_topic.most_common():
        print(f"  {t:40s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
