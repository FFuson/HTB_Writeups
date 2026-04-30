"""Fase 2: aumenta `machines.json` con enlaces a writeups de la lista
blanca.

Cada descubridor (`finder_*`) recibe una máquina y devuelve writeups
nuevos. Se mantienen en módulos pequeños para que añadir un autor sea
trivial: implementa una función `finder_xxx(machine) -> list[dict]` y
añádela a la lista `FINDERS`.

Política: nunca inventamos URLs. Si no podemos descubrirlas con
certeza, las dejamos al `validate_links.py` para que las purgue.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from typing import Callable
from xml.etree import ElementTree as ET

import requests

from scripts.cache import JsonCache
from scripts.config import (
    AUTHORS,
    HTTP_TIMEOUT,
    MACHINES_FILE,
    USER_AGENT,
)


# Caches en disco con TTL. Persisten entre runs.
# `_MISSING` marca "ya consultado y sin resultado" para no rascar dos
# veces lo mismo en runs sucesivos dentro del TTL.
_MISSING = "__missing__"
_yt_cache = JsonCache("youtube_videos", ttl_days=7)
_sitemap_cache = JsonCache("sitemaps", ttl_days=3)


def _http_get(url: str, **kwargs) -> requests.Response | None:
    try:
        return requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=HTTP_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        print(f"[find] GET {url} falló: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# YouTube — scraper para extraer el primer videoId de una búsqueda en un
# canal concreto. Sin clave de API, sin oauth: parseamos el blob
# `ytInitialData` que YouTube embebe en el HTML de la página.
# ---------------------------------------------------------------------------

# Anclamos a un bloque `videoRenderer` para evitar capturar videoIds de
# miniaturas, vídeos sugeridos o headers que YouTube embebe fuera de
# los resultados de búsqueda reales.
_VIDEO_ID_RE = re.compile(
    r'"videoRenderer":\s*\{[^{}]*?"videoId":"([A-Za-z0-9_-]{11})"'
)

# YouTube exige un User-Agent de navegador o redirige a la pantalla de
# consentimiento. Con un UA de "scraper" la cookie SOCS no basta.
_YT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Cookie que confirma consentimiento y evita la redirección a
# consent.youtube.com desde la UE. `CONSENT=YES+1` (formato antiguo) ya
# no funciona; el actual es `SOCS=CAI`.
_YT_COOKIES = {"SOCS": "CAI"}

def _youtube_first_video_id(handle: str, query: str) -> str | None:
    key = (handle, query)
    cached = _yt_cache.get(key, _MISSING)
    if cached is not _MISSING:
        return cached if cached else None

    url = (
        f"https://www.youtube.com/@{handle}/search"
        f"?query={urllib.parse.quote(query)}"
    )
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _YT_UA, "Accept-Language": "en-US,en;q=0.9"},
            cookies=_YT_COOKIES,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"[find] YouTube scrape falló para '{query}': {exc}", file=sys.stderr)
        # No cacheamos errores transitorios — reintentaremos en el
        # próximo run.
        return None

    if resp.status_code != 200 or "consent.youtube.com" in resp.url:
        _yt_cache.set(key, "")
        return None

    m = _VIDEO_ID_RE.search(resp.text)
    video_id = m.group(1) if m else ""
    _yt_cache.set(key, video_id)
    return video_id or None


# ---------------------------------------------------------------------------
# IppSec — usa la API pública de ippsec.rocks
# ---------------------------------------------------------------------------

_IPPSEC_CACHE: dict[str, list[dict]] | None = None


def _ippsec_dataset() -> dict[str, list[dict]]:
    """Indexa el dataset de IppSec por nombre de máquina.

    Probamos varias rutas porque el sitio ha cambiado de esquema más de
    una vez. Cada vídeo expone alguna combinación de `name`, `machine`
    o `title`, y el id de YouTube en `video_id`/`youtube_id`/`id`.
    """
    global _IPPSEC_CACHE
    if _IPPSEC_CACHE is not None:
        return _IPPSEC_CACHE

    candidates = [
        "https://ippsec.rocks/dataset.json",
        "https://ippsec.rocks/data/all.json",
        "https://raw.githubusercontent.com/IppSec/ippsec.rocks/master/dataset.json",
    ]

    videos: list[dict] = []
    for url in candidates:
        resp = _http_get(url)
        if not resp or resp.status_code != 200:
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        if isinstance(payload, dict):
            payload = payload.get("videos") or payload.get("data") or []
        if isinstance(payload, list) and payload:
            videos = payload
            break

    index: dict[str, list[dict]] = {}
    for video in videos:
        if not isinstance(video, dict):
            continue
        name = (
            video.get("name")
            or video.get("machine")
            or video.get("title")
            or ""
        ).strip().lower()
        if not name:
            continue
        index.setdefault(name, []).append(video)
    _IPPSEC_CACHE = index
    return index


def finder_ippsec(machine: dict) -> list[dict]:
    name = (machine.get("name") or "").strip().lower()
    if not name:
        return []

    found: list[dict] = []

    # 1) Intento por dataset (cuando ippsec.rocks publique uno parseable)
    for video in _ippsec_dataset().get(name, []):
        video_id = (
            video.get("video_id")
            or video.get("youtube_id")
            or video.get("id")
        )
        if not video_id:
            continue
        found.append({
            "autor": "IppSec",
            "idioma": "EN",
            "formato": "Vídeo",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    # 2) Scrape: primer videoId del canal @ippsec para "HackTheBox <name>"
    if not found:
        video_id = _youtube_first_video_id(
            handle="ippsec",
            query=f"HackTheBox {machine['name']}",
        )
        if video_id:
            found.append({
                "autor": "IppSec",
                "idioma": "EN",
                "formato": "Vídeo",
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

    # 3) Último recurso: búsqueda en el canal (no es video directo, pero
    # al menos el primer resultado es el correcto).
    if not found:
        query = urllib.parse.quote(f"HackTheBox {machine['name']}")
        found.append({
            "autor": "IppSec",
            "idioma": "EN",
            "formato": "Vídeo",
            "url": f"https://www.youtube.com/@ippsec/search?query={query}",
        })

    return found


# ---------------------------------------------------------------------------
# 0xdf — descubre por sitemap.xml
# ---------------------------------------------------------------------------

_OXDF_URLS: list[str] | None = None


def _oxdf_url_index() -> list[str]:
    global _OXDF_URLS
    if _OXDF_URLS is not None:
        return _OXDF_URLS

    cached = _sitemap_cache.get("0xdf")
    if cached:
        _OXDF_URLS = cached
        return _OXDF_URLS

    resp = _http_get("https://0xdf.gitlab.io/sitemap.xml")
    if not resp or resp.status_code != 200:
        _OXDF_URLS = []
        return _OXDF_URLS

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        _OXDF_URLS = []
        return _OXDF_URLS

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [el.text for el in root.findall(".//sm:loc", ns) if el.text]
    _OXDF_URLS = urls
    _sitemap_cache.set("0xdf", urls)
    return urls


def finder_0xdf(machine: dict) -> list[dict]:
    name = (machine.get("name") or "").strip().lower()
    if not name:
        return []

    pattern = re.compile(rf"/htb-{re.escape(name)}(?:[-/]|\.html?$|$)", re.IGNORECASE)
    matches = [u for u in _oxdf_url_index() if pattern.search(u)]

    return [
        {"autor": "0xdf", "idioma": "EN", "formato": "Texto", "url": u}
        for u in matches
    ]


# ---------------------------------------------------------------------------
# El Pingüino de Mario — scraping de su canal de YouTube
# (no tiene blog propio, todo el contenido HTB vive en YouTube)
# ---------------------------------------------------------------------------

def finder_pinguino(machine: dict) -> list[dict]:
    name = (machine.get("name") or "").strip()
    if not name:
        return []
    video_id = _youtube_first_video_id(
        handle="elpinguinodemario",
        query=f"HackTheBox {name}",
    )
    if not video_id:
        return []
    return [{
        "autor": "El Pingüino de Mario",
        "idioma": "ES",
        "formato": "Vídeo",
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }]


# ---------------------------------------------------------------------------
# S4vitar — sólo si htbmachines no nos lo dio en fetch_machines
# ---------------------------------------------------------------------------

def finder_s4vitar(machine: dict) -> list[dict]:
    """Sólo se invoca cuando htbmachines no aportó un vídeo directo de
    S4vitar. En ese caso intentamos sacar uno del canal @s4vitar; si
    tampoco aparece, dejamos la máquina sin entrada de S4vitar (mejor
    nada que una búsqueda genérica que no resuelve nada).
    """
    has_s4 = any(w.get("autor") == "S4vitar" for w in machine.get("writeups", []))
    if has_s4:
        return []
    name = (machine.get("name") or "").strip()
    if not name:
        return []

    video_id = _youtube_first_video_id(
        handle="s4vitar",
        query=f"HackTheBox {name}",
    )
    if not video_id:
        return []

    return [{
        "autor": "S4vitar",
        "idioma": "ES",
        "formato": "Vídeo",
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }]


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

FINDERS: list[Callable[[dict], list[dict]]] = [
    finder_ippsec,
    finder_0xdf,
    finder_pinguino,
    finder_s4vitar,
]


def _author_known(name: str) -> bool:
    return name in AUTHORS


def augment(machines: list[dict]) -> list[dict]:
    for machine in machines:
        existing_urls = {w["url"] for w in machine.get("writeups", []) if w.get("url")}
        for finder in FINDERS:
            try:
                new_writeups = finder(machine)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[find] {finder.__name__} explotó en {machine['name']}: {exc}",
                    file=sys.stderr,
                )
                continue
            for w in new_writeups:
                if not _author_known(w.get("autor", "")):
                    continue
                url = w.get("url")
                if not url or url in existing_urls:
                    continue
                machine.setdefault("writeups", []).append(w)
                existing_urls.add(url)
    return machines


def main() -> int:
    if not MACHINES_FILE.exists():
        print(
            f"[find] {MACHINES_FILE} no existe. Ejecuta primero fetch_machines.",
            file=sys.stderr,
        )
        return 1

    machines = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    augment(machines)

    MACHINES_FILE.write_text(
        json.dumps(machines, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _yt_cache.save()
    _sitemap_cache.save()

    total_writeups = sum(len(m.get("writeups", [])) for m in machines)
    print(
        f"[find] {len(machines)} máquinas · {total_writeups} writeups tras agregación"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
