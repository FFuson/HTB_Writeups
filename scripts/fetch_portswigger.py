"""Fase 1 (PortSwigger): catálogo de labs de PortSwigger Web Security
Academy.

Estrategia:
    1. Fetch del sitemap.xml de PortSwigger.
    2. Filtrar URLs que matchen `/web-security/<topic>/lab-<slug>`.
    3. Por cada lab, fetch del HTML y extraer:
         - title (h1.heading-2, sin prefijo "Lab: ")
         - description (meta[name="description"])
         - topic (de la URL)

La dificultad (Apprentice/Practitioner/Expert) NO se extrae porque
las topic-pages son JS-rendered (no scrapeables sin headless browser).
Queda como TODO para Phase 2.5 vía mapping manual o headless scrape.

Salida: `data/portswigger_labs.json` con un array de objetos:
    {
        "id": "sql-injection-lab-login-bypass",
        "platform": "portswigger",
        "name": "SQL injection vulnerability allowing login bypass",
        "topic_id": "sql-injection",
        "topic_label": "SQL injection",
        "difficulty": null,
        "url_official": "https://portswigger.net/web-security/...",
        "writeups": [
            {"autor": "PortSwigger", "idioma": "EN", "formato": "Texto",
             "url": "https://portswigger.net/web-security/...#solution"},
        ],
        "skills": ""
    }
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from typing import Iterable

import requests

from scripts.config import DATA_DIR, USER_AGENT, HTTP_TIMEOUT

PORTSWIGGER_SITEMAP = "https://portswigger.net/sitemap.xml"
LAB_URL_RE = re.compile(
    r"https://portswigger\.net/web-security/([a-z-]+)/lab-([a-z0-9-]+)"
)
PORTSWIGGER_LABS_FILE = DATA_DIR / "portswigger_labs.json"

# Política de scraping: pausa entre requests para no estresar el origin.
# 95 labs × 0.4 s ≈ 40 s total. PortSwigger no rate-limita pero somos majos.
SLEEP_BETWEEN_REQS = 0.4

# Topic IDs cuyo label humano-legible difiere de "title-casing" trivial.
TOPIC_LABEL_OVERRIDES = {
    "sql-injection": "SQL Injection",
    "xxe": "XXE (XML External Entity)",
    "ssrf": "SSRF (Server-Side Request Forgery)",
    "csrf": "CSRF (Cross-Site Request Forgery)",
    "cors": "CORS",
    "jwt": "JWT (JSON Web Tokens)",
    "oauth": "OAuth Authentication",
    "graphql": "GraphQL",
    "llm-attacks": "LLM Attacks",
    "nosql-injection": "NoSQL Injection",
    "os-command-injection": "OS Command Injection",
    "request-smuggling": "HTTP Request Smuggling",
    "race-conditions": "Race Conditions",
    "file-path-traversal": "Directory / Path Traversal",
    "file-upload": "File Upload Vulnerabilities",
    "websockets": "WebSockets",
    "web-cache-deception": "Web Cache Deception",
    "api-testing": "API Testing",
    "access-control": "Access Control Vulnerabilities",
    "clickjacking": "Clickjacking",
}


def _topic_label(topic_id: str) -> str:
    if topic_id in TOPIC_LABEL_OVERRIDES:
        return TOPIC_LABEL_OVERRIDES[topic_id]
    return topic_id.replace("-", " ").title()


def fetch_lab_urls(session: requests.Session) -> list[str]:
    """Devuelve la lista de URLs de labs en el sitemap, en orden."""
    resp = session.get(PORTSWIGGER_SITEMAP, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    urls = sorted(set(LAB_URL_RE.findall(resp.text)))
    # findall devuelve (topic, slug) tuples. Reconstruir las URLs:
    return [
        f"https://portswigger.net/web-security/{topic}/lab-{slug}"
        for topic, slug in urls
    ]


_TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*heading-2[^"]*"[^>]*>([^<]+)</h1>'
)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.IGNORECASE
)


def parse_lab_page(html_text: str) -> dict[str, str]:
    """Extrae title + description del HTML de un lab. Devuelve dict
    con keys "name" y "description" (vacíos si no encuentra)."""
    name = ""
    desc = ""
    m = _TITLE_RE.search(html_text)
    if m:
        raw = html.unescape(m.group(1)).strip()
        # Strip "Lab: " prefix si lo lleva.
        if raw.lower().startswith("lab:"):
            raw = raw[4:].strip()
        name = raw
    m = _META_DESC_RE.search(html_text)
    if m:
        desc = html.unescape(m.group(1)).strip()
    return {"name": name, "description": desc}


def lab_id_from_url(url: str) -> str:
    """ID estable: <topic>-<lab-slug-sin-prefijo-lab-->.

    Ejemplo:
        https://.../sql-injection/lab-login-bypass
        → "sql-injection-login-bypass"
    """
    m = LAB_URL_RE.match(url)
    if not m:
        raise ValueError(f"URL no parseable: {url}")
    topic, slug = m.group(1), m.group(2)
    return f"{topic}-{slug}"


def lab_topic_from_url(url: str) -> str:
    m = LAB_URL_RE.match(url)
    if not m:
        raise ValueError(f"URL no parseable: {url}")
    return m.group(1)


def lab_slug_from_url(url: str) -> str:
    """Slug interno (lab-<x> → <x>) — usado en URLs rootea.es."""
    m = LAB_URL_RE.match(url)
    if not m:
        raise ValueError(f"URL no parseable: {url}")
    return m.group(2)


def fetch_lab(session: requests.Session, url: str) -> dict | None:
    """Fetch + parse de un lab. Devuelve dict con la entrada normalizada,
    o None si la página no responde 200 o no extrae título."""
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"[portswigger] {url} falló: {exc}", file=sys.stderr)
        return None
    if resp.status_code != 200:
        print(
            f"[portswigger] {url} HTTP {resp.status_code}, salto",
            file=sys.stderr,
        )
        return None
    parsed = parse_lab_page(resp.text)
    if not parsed["name"]:
        print(
            f"[portswigger] {url} sin h1, salto",
            file=sys.stderr,
        )
        return None
    topic_id = lab_topic_from_url(url)
    return {
        "id": lab_id_from_url(url),
        "platform": "portswigger",
        "name": parsed["name"],
        "topic_id": topic_id,
        "topic_label": _topic_label(topic_id),
        "difficulty": None,  # TODO Phase 2.5: scrape topic page o curate manual
        "url_official": url,
        "description": parsed["description"],
        "writeups": [
            {
                "autor": "PortSwigger",
                "idioma": "EN",
                "formato": "Texto",
                "url": f"{url}",
            },
        ],
        # `skills` se rellena en find_skills.py via matching del título +
        # descripción contra el alias index. Topic_label es la skill
        # primaria por defecto.
        "skills": parsed["name"] + " " + parsed["description"] + " " + _topic_label(topic_id),
    }


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            # PortSwigger acepta UAs raros pero un UA browser-like
            # reduce la probabilidad de bloqueos accidentales.
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        urls = fetch_lab_urls(session)
    except requests.RequestException as exc:
        print(f"[portswigger] sitemap falló: {exc}", file=sys.stderr)
        return 1

    if not urls:
        print("[portswigger] sitemap no devolvió labs", file=sys.stderr)
        return 1

    print(f"[portswigger] sitemap: {len(urls)} URLs de labs")

    labs: list[dict] = []
    for i, url in enumerate(urls, start=1):
        lab = fetch_lab(session, url)
        if lab is not None:
            labs.append(lab)
        if i % 20 == 0:
            print(f"[portswigger]   procesadas {i}/{len(urls)}")
        time.sleep(SLEEP_BETWEEN_REQS)

    # Ordenar por (topic, name) para output estable.
    labs.sort(key=lambda l: (l["topic_id"], l["name"].lower()))

    PORTSWIGGER_LABS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTSWIGGER_LABS_FILE.write_text(
        json.dumps(labs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Stats
    by_topic: dict[str, int] = {}
    for lab in labs:
        by_topic[lab["topic_id"]] = by_topic.get(lab["topic_id"], 0) + 1
    print(
        f"[portswigger] OK · {len(labs)} labs guardados en "
        f"{PORTSWIGGER_LABS_FILE}"
    )
    breakdown = ", ".join(
        f"{t}={n}" for t, n in sorted(by_topic.items(), key=lambda kv: -kv[1])
    )
    print(f"[portswigger]   por topic: {breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
