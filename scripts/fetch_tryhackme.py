"""Catálogo de rooms de TryHackMe.

Fuente: API pública sin auth (`/api/v2/rooms/details` y `/api/v2/rooms/tasks`).
Cloudflare bloquea peticiones HTTP planas tras ~60 reqs (`cf-mitigated:
challenge`). Workaround: usar Playwright para abrir homepage, dejar que
el browser resuelva el reto JS, y luego hacer las llamadas API desde el
mismo `context.request` (mismas cookies + fingerprint de browser).

Eficiente: ~0.4s/room × 1000 rooms × 2 endpoints = ~14 min total.
Cacheado JSON con TTL 30 días — re-runs casi instantáneos.

Salida: data/tryhackme_rooms.json
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
import time
from collections import Counter

from playwright.sync_api import sync_playwright

from scripts.cache import JsonCache
from scripts.config import DATA_DIR

TRYHACKME_SITEMAP = "https://tryhackme.com/sitemaps/rooms.xml"
TRYHACKME_HOMEPAGE = "https://tryhackme.com"
TRYHACKME_DETAILS_URL = "https://tryhackme.com/api/v2/rooms/details"
TRYHACKME_TASKS_URL = "https://tryhackme.com/api/v2/rooms/tasks"
TRYHACKME_ROOMS_FILE = DATA_DIR / "tryhackme_rooms.json"

ROOM_SLUG_RE = re.compile(r"https://tryhackme\.com/room/([a-z0-9-]+)")

_details_cache = JsonCache("tryhackme_details", ttl_days=30)
_tasks_cache = JsonCache("tryhackme_tasks", ttl_days=30)

# Pace entre llamadas API. CF challenge se dispara con ráfagas rápidas
# (~30 req/s). 0.3s/call = 3 req/s queda muy por debajo del umbral.
# Plus, batches: pausa más larga cada N reqs por si hay quotas adicionales.
SLEEP_PER_REQ = 0.3
SLEEP_PER_BATCH = 5
BATCH_SIZE = 100


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_skills_text(details: dict, tasks: list) -> str:
    """Concatena title + description + texto de cada question. Las
    questions de TryHackMe mencionan tools (nmap, metasploit, mimikatz)
    y CVEs (`ms??-???`), excelente input para el alias-matching.

    Defensivo: si `tasks` no es lista o un task no es dict, lo salta
    silenciosamente (la API a veces devuelve estructuras inesperadas
    para rooms recién creadas o con metadatos parciales).
    """
    parts: list[str] = [
        details.get("title", ""),
        _strip_html(details.get("description", "")),
    ]
    if not isinstance(tasks, list):
        return " ".join(p for p in parts if p)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for q in task.get("questions", []) or []:
            if not isinstance(q, dict):
                continue
            qt = _strip_html(q.get("question", ""))
            if qt:
                parts.append(qt)
            ht = _strip_html(q.get("hint", ""))
            if ht:
                parts.append(ht)
    return " ".join(p for p in parts if p)


def _api_get(context, url: str, slug: str, params: dict | None = None) -> dict | None:
    """GET vía context.request (bypassea Cloudflare). Devuelve `data`
    payload o None si error."""
    try:
        resp = context.request.get(url, params=params or {}, timeout=15_000)
    except Exception as exc:  # noqa: BLE001
        print(f"[thm]   {slug}: red error: {exc}", file=sys.stderr)
        return None
    if not resp.ok:
        return None
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if payload.get("status") != "success":
        return None
    return payload.get("data")


def _fetch_room_data(context, slug: str) -> dict | None:
    """Fetch detalles + tasks. Cacheado en disco — re-runs son rápidos."""
    details_cached = _details_cache.get(slug)
    tasks_cached = _tasks_cache.get(slug)

    # Cache hit completo
    if details_cached is not None and tasks_cached is not None:
        if not details_cached:  # sentinel "not found"
            return None
        return _build_room_dict(slug, details_cached, tasks_cached)

    # Fetch lo que falta
    details = details_cached if details_cached is not None else _api_get(
        context, TRYHACKME_DETAILS_URL, slug, {"roomCode": slug}
    )
    if details is None:
        _details_cache.set(slug, {})
        return None
    if details_cached is None:
        _details_cache.set(slug, details)

    tasks = tasks_cached if tasks_cached is not None else _api_get(
        context, TRYHACKME_TASKS_URL, slug, {"roomCode": slug}
    )
    if tasks is None:
        tasks = []
    if tasks_cached is None:
        _tasks_cache.set(slug, tasks)

    return _build_room_dict(slug, details, tasks)


def _build_room_dict(slug: str, details: dict, tasks: list[dict]) -> dict | None:
    title = (details.get("title") or "").strip()
    if not title:
        return None
    url_official = f"https://tryhackme.com/room/{slug}"
    return {
        "id": f"tryhackme-{slug}",
        "platform": "tryhackme",
        "name": title,
        "url_slug": slug,
        "url_official": url_official,
        "description": _strip_html(details.get("description", "")),
        "type": (details.get("type") or "").lower() or None,
        "difficulty": (details.get("difficulty") or "").lower() or None,
        "free_to_use": bool(details.get("freeToUse", False)),
        "business_only": bool(details.get("businessOnly", False)),
        "users": details.get("users") or 0,
        "time_to_complete_min": details.get("timeToComplete") or None,
        "image_url": details.get("imageURL") or "",
        "header_image": details.get("headerImage") or "",
        "created": (details.get("created") or "")[:10],
        "writeups": [
            {
                "autor": "TryHackMe",
                "idioma": "EN",
                "formato": "Lab oficial",
                "url": url_official,
            },
        ],
        "skills": _build_skills_text(details, tasks),
        "n_tasks": len(tasks) if isinstance(tasks, list) else 0,
        "n_questions": sum(
            len(t.get("questions") or []) for t in tasks
            if isinstance(t, dict)
        ) if isinstance(tasks, list) else 0,
    }


def fetch_room_slugs() -> list[str]:
    """Lista de slugs únicos del sitemap, ordenada."""
    import requests
    try:
        resp = requests.get(
            TRYHACKME_SITEMAP, timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[thm] sitemap falló: {exc}", file=sys.stderr)
        return []
    return sorted(set(ROOM_SLUG_RE.findall(resp.text)))


def main(argv: list[str] | None = None) -> int:
    slugs = fetch_room_slugs()
    print(f"[thm] sitemap: {len(slugs)} rooms candidatas")
    if not slugs:
        return 1

    # Pre-check: si todos los slugs ya están en cache, podemos saltar
    # el spin-up de Playwright entero.
    needs_fetch = [
        s for s in slugs
        if _details_cache.get(s) is None or _tasks_cache.get(s) is None
    ]
    print(f"[thm] cache: {len(slugs) - len(needs_fetch)} hits, "
          f"{len(needs_fetch)} a fetchear")

    rooms: list[dict] = []
    failed = 0

    if not needs_fetch:
        # Solo reconstruir desde cache
        for slug in slugs:
            r = _fetch_room_data(None, slug)
            if r is None:
                failed += 1
            else:
                rooms.append(r)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            print(f"[thm] resolviendo CF challenge en homepage…")
            page.goto(TRYHACKME_HOMEPAGE,
                      wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            print(f"[thm] cookies: {len(context.cookies())}")

            for i, slug in enumerate(slugs, start=1):
                room = _fetch_room_data(context, slug)
                if room is None:
                    failed += 1
                else:
                    rooms.append(room)
                # Rate limit anti-CF
                if slug in needs_fetch:
                    time.sleep(SLEEP_PER_REQ)
                if i % BATCH_SIZE == 0:
                    print(f"[thm]   {i}/{len(slugs)} (ok {len(rooms)}, "
                          f"err {failed})")
                    _details_cache.save()
                    _tasks_cache.save()
                    time.sleep(SLEEP_PER_BATCH)

            browser.close()

    _details_cache.save()
    _tasks_cache.save()

    rooms.sort(key=lambda r: (r.get("difficulty") or "z", r["name"].lower()))

    # Preserve fields añadidos por fases posteriores del pipeline
    # (find_skills agrega skill_links/related_skills, etc.). Sin esto,
    # cada re-run de fetch_tryhackme borraba esos campos y forzaba
    # re-correr find_skills.
    if TRYHACKME_ROOMS_FILE.exists():
        try:
            prev = {
                r["id"]: r for r in json.loads(
                    TRYHACKME_ROOMS_FILE.read_text(encoding="utf-8")
                )
            }
        except (OSError, json.JSONDecodeError):
            prev = {}
        for room in rooms:
            old = prev.get(room["id"])
            if not old:
                continue
            for field in ("skill_links", "related_skills"):
                if old.get(field) and not room.get(field):
                    room[field] = old[field]
            # Writeups: preservar entradas de autores whitelist (no las
            # del propio TryHackMe, que se regeneran).
            extra_writeups = [
                w for w in old.get("writeups", [])
                if w.get("autor") and w.get("autor") != "TryHackMe"
            ]
            if extra_writeups:
                existing_urls = {w.get("url") for w in room.get("writeups", [])}
                for w in extra_writeups:
                    if w.get("url") not in existing_urls:
                        room.setdefault("writeups", []).append(w)

    TRYHACKME_ROOMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRYHACKME_ROOMS_FILE.write_text(
        json.dumps(rooms, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[thm] OK · {len(rooms)} rooms guardadas en {TRYHACKME_ROOMS_FILE}")
    print(f"[thm]   fallidas / no encontradas: {failed}")

    by_diff = Counter(r.get("difficulty") or "?" for r in rooms)
    by_type = Counter(r.get("type") or "?" for r in rooms)
    free = sum(1 for r in rooms if r.get("free_to_use"))
    biz = sum(1 for r in rooms if r.get("business_only"))
    print(f"[thm]   difficulty: {dict(by_diff)}")
    print(f"[thm]   type: {dict(by_type)}")
    print(f"[thm]   free: {free} · subscriber-only: "
          f"{len(rooms) - free - biz} · business-only: {biz}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
