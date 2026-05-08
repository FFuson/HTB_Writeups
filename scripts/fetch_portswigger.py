"""Catálogo de labs de PortSwigger Web Security Academy.

Fuentes (en orden de preferencia):
    1. `data/portswigger_seed.json` — generado por
       `scripts/scrape_portswigger_extended.py` (Playwright one-shot,
       cubre 260+ labs con difficulty). Esta es la fuente primaria.
    2. Sitemap de PortSwigger — fallback resiliente que cubre ~95 labs
       sin difficulty. Se usa solo si el seed no existe o falta cubrir
       URLs nuevas que aún no están en el seed.

Por cada lab fetcheamos su página HTML (cacheada en disco) para
extraer la `description` del meta-tag.

Salida: `data/portswigger_labs.json`.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time

import requests

from scripts.cache import JsonCache
from scripts.config import DATA_DIR, USER_AGENT, HTTP_TIMEOUT

PORTSWIGGER_SITEMAP = "https://portswigger.net/sitemap.xml"
PORTSWIGGER_LABS_FILE = DATA_DIR / "portswigger_labs.json"
PORTSWIGGER_SEED_FILE = DATA_DIR / "portswigger_seed.json"

# Pattern: optional sub-topic before /lab-<slug>.
# https://portswigger.net/web-security/<topic>/[<subtopic>/]lab-<slug>
LAB_URL_RE = re.compile(
    r"^https://portswigger\.net/web-security/"
    r"([a-z-]+)(?:/([a-z-]+))?/lab-([a-z0-9-]+)/?$"
)
LAB_URL_FINDALL = re.compile(
    r"https://portswigger\.net/web-security/"
    r"[a-z-]+(?:/[a-z-]+)?/lab-[a-z0-9-]+"
)

SLEEP_BETWEEN_REQS = 0.25
DESCRIPTION_CACHE_TTL_DAYS = 60


# Topic IDs cuyo label humano-legible difiere de "title-casing" trivial.
TOPIC_LABEL_OVERRIDES = {
    "sql-injection": "SQL Injection",
    "cross-site-scripting": "Cross-Site Scripting (XSS)",
    "dom-based": "DOM-based Vulnerabilities",
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
    "web-cache-poisoning": "Web Cache Poisoning",
    "api-testing": "API Testing",
    "access-control": "Access Control Vulnerabilities",
    "clickjacking": "Clickjacking",
    "authentication": "Authentication Vulnerabilities",
    "deserialization": "Insecure Deserialization",
    "logic-flaws": "Business Logic Vulnerabilities",
    "host-header": "HTTP Host Header Attacks",
    "information-disclosure": "Information Disclosure",
    "prototype-pollution": "Prototype Pollution",
    "server-side-template-injection": "Server-Side Template Injection (SSTI)",
    "essential-skills": "Essential Skills",
}


def _topic_label(topic_id: str) -> str:
    if topic_id in TOPIC_LABEL_OVERRIDES:
        return TOPIC_LABEL_OVERRIDES[topic_id]
    return topic_id.replace("-", " ").title()


def _unique_slug(url: str) -> str:
    """Slug único site-wide. Combina subtopic + slug-after-`lab-` para
    evitar colisiones cuando dos labs en sub-topics distintos comparten
    el mismo nombre interno (ocurre en cross-site-scripting).
    """
    m = LAB_URL_RE.match(url)
    if not m:
        return "lab"
    _topic, subtopic, slug = m.group(1), m.group(2), m.group(3)
    if subtopic:
        return f"{subtopic}-{slug}"
    return slug


def _lab_id(url: str) -> str:
    """ID estable y único para Giscus / cross-references. Combina topic
    + slug único. Ejemplo: cross-site-scripting-reflected-html-context-nothing-encoded.
    """
    m = LAB_URL_RE.match(url)
    if not m:
        return f"lab-{abs(hash(url)) % 10**8}"
    return f"{m.group(1)}-{_unique_slug(url)}"


def fetch_lab_urls_from_sitemap(session: requests.Session) -> list[str]:
    try:
        resp = session.get(PORTSWIGGER_SITEMAP, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[portswigger] sitemap falló: {exc}", file=sys.stderr)
        return []
    return sorted(set(LAB_URL_FINDALL.findall(resp.text)))


def load_seed() -> list[dict]:
    """Carga `portswigger_seed.json` (output de scrape_portswigger_extended).
    Devuelve lista de dicts con keys {url, name, topic_id, slug, difficulty}.
    """
    if not PORTSWIGGER_SEED_FILE.exists():
        return []
    try:
        return json.loads(
            PORTSWIGGER_SEED_FILE.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        print(
            f"[portswigger] seed corrupto: {exc}",
            file=sys.stderr,
        )
        return []


_TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*heading-2[^"]*"[^>]*>([^<]+)</h1>'
)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.IGNORECASE
)


_description_cache = JsonCache("portswigger_descriptions", ttl_days=DESCRIPTION_CACHE_TTL_DAYS)


def fetch_lab_description(
    session: requests.Session, url: str, fallback_name: str = ""
) -> tuple[str, str]:
    """Devuelve `(name, description)`. Cachea la respuesta en disco para
    evitar refetcheos en siguientes runs (descripción cambia poco).
    """
    cached = _description_cache.get(url)
    if cached is not None:
        return cached.get("name", fallback_name), cached.get("description", "")
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        print(f"[portswigger]   {url} falló: {exc}", file=sys.stderr)
        return fallback_name, ""
    if resp.status_code != 200:
        return fallback_name, ""
    text = resp.text
    name = fallback_name
    desc = ""
    m = _TITLE_RE.search(text)
    if m:
        raw = html.unescape(m.group(1)).strip()
        if raw.lower().startswith("lab:"):
            raw = raw[4:].strip()
        if raw:
            name = raw
    m = _META_DESC_RE.search(text)
    if m:
        desc = html.unescape(m.group(1)).strip()
    _description_cache.set(url, {"name": name, "description": desc})
    return name, desc


def _build_lab(
    url: str,
    seed_entry: dict | None,
    session: requests.Session,
) -> dict | None:
    m = LAB_URL_RE.match(url)
    if not m:
        return None
    topic_id = m.group(1)
    fallback_name = (seed_entry or {}).get("name", "")
    name, desc = fetch_lab_description(session, url, fallback_name)
    if not name:
        return None
    difficulty = (seed_entry or {}).get("difficulty")
    return {
        "id": _lab_id(url),
        "platform": "portswigger",
        "name": name,
        "topic_id": topic_id,
        "topic_label": _topic_label(topic_id),
        "difficulty": difficulty,
        "url_official": url,
        "url_slug": _unique_slug(url),
        "description": desc,
        "writeups": [
            {
                "autor": "PortSwigger",
                "idioma": "EN",
                "formato": "Texto",
                "url": url,
            },
        ],
        # El alias-matching de find_skills.py opera sobre este texto.
        "skills": f"{name} {desc} {_topic_label(topic_id)}",
    }


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })

    seed = load_seed()
    seed_by_url = {s["url"]: s for s in seed if s.get("url")}
    print(f"[portswigger] seed: {len(seed_by_url)} labs (con difficulty)")

    sitemap_urls = fetch_lab_urls_from_sitemap(session)
    print(f"[portswigger] sitemap: {len(sitemap_urls)} URLs de labs")

    # Unión: seed primero (orden determinista), sitemap luego para
    # capturar labs nuevos no rastreados aún por el scrape extendido.
    all_urls: list[str] = []
    seen: set[str] = set()
    for url in list(seed_by_url.keys()) + sitemap_urls:
        url = url.rstrip("/")
        if url in seen:
            continue
        seen.add(url)
        all_urls.append(url)
    print(f"[portswigger] union: {len(all_urls)} URLs únicas a procesar")

    if not all_urls:
        print("[portswigger] ningún lab encontrado", file=sys.stderr)
        return 1

    labs: list[dict] = []
    for i, url in enumerate(all_urls, start=1):
        lab = _build_lab(url, seed_by_url.get(url), session)
        if lab is not None:
            labs.append(lab)
        if i % 30 == 0:
            print(f"[portswigger]   procesadas {i}/{len(all_urls)}")
        time.sleep(SLEEP_BETWEEN_REQS)

    _description_cache.save()

    labs.sort(key=lambda l: (l["topic_id"], l["name"].lower()))
    PORTSWIGGER_LABS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTSWIGGER_LABS_FILE.write_text(
        json.dumps(labs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    by_topic: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for lab in labs:
        by_topic[lab["topic_id"]] = by_topic.get(lab["topic_id"], 0) + 1
        d = lab.get("difficulty") or "Unknown"
        by_difficulty[d] = by_difficulty.get(d, 0) + 1
    print(
        f"[portswigger] OK · {len(labs)} labs guardados en "
        f"{PORTSWIGGER_LABS_FILE}"
    )
    print(f"[portswigger]   difficulty: {by_difficulty}")
    breakdown = ", ".join(
        f"{t}={n}" for t, n in sorted(by_topic.items(), key=lambda kv: -kv[1])
    )
    print(f"[portswigger]   por topic: {breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
