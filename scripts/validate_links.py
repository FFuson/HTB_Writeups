"""Fase 3: pasa un HEAD a cada URL y descarta las muertas.

Concurrente con `ThreadPoolExecutor` porque hacer cientos de peticiones
secuenciales sería un castigo. Algunos hosts (YouTube, Cloudflare) no
contestan bien a HEAD: para esos hacemos fallback a un GET con
`stream=True` y cerramos la conexión sin leer el cuerpo.

Cada hilo usa su propio `requests.Session` (almacenado en
`threading.local`) para reutilizar conexiones TCP/TLS.
"""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.cache import JsonCache
from scripts.config import (
    HTTP_CONCURRENCY,
    HTTP_TIMEOUT,
    MACHINES_FILE,
    SKILL_DOMAINS,
    USER_AGENT,
    WHITELIST_DOMAINS,
)


# Cache de URLs validadas. TTL corto: una URL puede morir/revivir en
# semanas, no queremos arrastrar un veredicto antiguo demasiado tiempo.
_url_cache = JsonCache("url_health", ttl_days=7)

# Hosts donde HEAD suele mentir (devuelve 405, 403 o redirecciones raras).
# Usamos match exacto para no aceptar "myyoutube.com" como YouTube.
HEAD_HOSTILE = {"youtube.com", "youtu.be"}

OK_STATUSES = {200, 201, 202, 203, 204, 301, 302, 303, 307, 308}

# Fallos AMBIGUOS. Todas las URLs que validamos son de dominios curados de
# calidad (whitelist). Un 403/404/429/5xx desde el IP de CI/datacenter casi
# siempre es bot-blocking o un problema transitorio, NO que la página haya
# desaparecido — p.ej. PortSwigger devuelve 404 a peticiones automatizadas
# para páginas que existen y dan 200 en un navegador normal. Ante estos
# statuses CONSERVAMOS el enlace (no podamos) y no cacheamos el veredicto,
# para reintentar en el próximo run (y que un run desde IP buena reconcilie).
SOFT_FAIL_STATUSES = {403, 404, 408, 425, 429, 500, 502, 503, 504, 522, 524}

_thread_local = threading.local()


_RETRY = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=(500, 502, 503, 504, 522, 524),
    allowed_methods=frozenset(["HEAD", "GET"]),
    raise_on_status=False,
)


def _session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        adapter = HTTPAdapter(max_retries=_RETRY, pool_connections=4, pool_maxsize=4)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _thread_local.session = s
    return s


def _normalize_host(host: str) -> str:
    h = host.lower().lstrip(".")
    while h.startswith(("www.", "m.")):
        h = h.split(".", 1)[1]
    return h


def _domain_in(url: str, allowed: set[str]) -> bool:
    host = _normalize_host(urlparse(url).hostname or "")
    if not host:
        return False
    allowed_lower = {d.lower() for d in allowed}
    if host in allowed_lower:
        return True
    return any(host.endswith("." + d) for d in allowed_lower)


def _domain_ok(url: str) -> bool:
    return _domain_in(url, WHITELIST_DOMAINS)


def _skill_domain_ok(url: str) -> bool:
    return _domain_in(url, SKILL_DOMAINS)


def _is_head_hostile(host: str) -> bool:
    h = _normalize_host(host)
    return h in HEAD_HOSTILE or any(h.endswith("." + x) for x in HEAD_HOSTILE)


def _check_url(url: str) -> tuple[str, str, int | None]:
    """Devuelve (url, verdict, status) con verdict ∈ {"alive","dead","soft"}.

    - "alive": status 2xx/3xx → enlace vivo.
    - "soft":  fallo ambiguo (403/404/429/5xx o error de red/timeout). Para
       nuestros dominios curados casi siempre es bot-block o transitorio →
       CONSERVAMOS el enlace y NO cacheamos (se reintenta en el próximo run).
    - "dead":  fallo NO ambiguo (p.ej. 410 Gone, 451, URL malformada) → podar.
    """
    if not url or not url.startswith(("http://", "https://")):
        return url, "dead", None

    sess = _session()
    host = (urlparse(url).hostname or "").lower()
    use_get = _is_head_hostile(host)

    try:
        if not use_get:
            resp = sess.head(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            if resp.status_code == 405:
                resp = sess.get(
                    url, timeout=HTTP_TIMEOUT, allow_redirects=True, stream=True
                )
                resp.close()
        else:
            resp = sess.get(
                url, timeout=HTTP_TIMEOUT, allow_redirects=True, stream=True
            )
            resp.close()
    except requests.RequestException:
        return url, "soft", None  # red/timeout: ambiguo, no podar

    code = resp.status_code
    if code in OK_STATUSES:
        return url, "alive", code
    if code in SOFT_FAIL_STATUSES:
        return url, "soft", code
    return url, "dead", code


def validate(machines: list[dict]) -> tuple[list[dict], dict]:
    """Devuelve (machines_filtradas, stats)."""
    # Recolectar todas las URLs únicas a validar (writeups + skill_links).
    urls: set[str] = set()
    for m in machines:
        for w in m.get("writeups", []):
            url = w.get("url", "")
            if url and _domain_ok(url):
                urls.add(url)
        for s in m.get("skill_links", []):
            url = s.get("url", "")
            if url and _skill_domain_ok(url):
                urls.add(url)

    # Particiona: las que tengamos en caché (veredicto DEFINITIVO) se resuelven
    # al instante. Los "soft" nunca se cachean, así que un miss = "sin
    # comprobar todavía".
    cached: dict[str, str] = {}
    pending: list[str] = []
    for u in urls:
        # Sólo confiamos en un "alive" cacheado. Un "dead" cacheado se
        # re-comprueba SIEMPRE: pudo cachearlo el código antiguo ante un
        # bot-block puntual, o el enlace puede haber revivido. Así el
        # catálogo se auto-cura sin purgar la caché a mano.
        if _url_cache.get(u) is True:
            cached[u] = "alive"
        else:
            pending.append(u)

    print(
        f"[validate] {len(urls)} URLs únicas · {len(cached)} en caché · "
        f"{len(pending)} a comprobar"
    )

    results: dict[str, str] = dict(cached)
    soft = 0
    if pending:
        with ThreadPoolExecutor(max_workers=HTTP_CONCURRENCY) as pool:
            futures = {pool.submit(_check_url, u): u for u in pending}
            for fut in as_completed(futures):
                url, verdict, status = fut.result()
                results[url] = verdict
                # Sólo cacheamos veredictos DEFINITIVOS (alive/dead). Los
                # "soft" (bot-block / transitorio) se reintentan cada run.
                if verdict == "alive":
                    _url_cache.set(url, True)
                elif verdict == "dead":
                    _url_cache.set(url, False)
                else:
                    soft += 1
                mark = {"alive": "✓", "dead": "✗", "soft": "~"}[verdict]
                print(f"[validate] {mark} {status or '---'} {url}")
    _url_cache.save()
    if soft:
        print(f"[validate] {soft} URLs con fallo ambiguo (bot-block / "
              f"transitorio) — se CONSERVAN, no se podan")

    # Un enlace se PODA sólo con veredicto "dead". "alive" y "soft" se
    # conservan (soft = no hay prueba de que esté muerto).
    def _keep(url: str) -> bool:
        return results.get(url, "soft") != "dead"

    # Filtrar writeups
    alive_writeups = 0
    dead_writeups = 0
    for m in machines:
        kept: list[dict] = []
        for w in m.get("writeups", []):
            url = w.get("url", "")
            if not _domain_ok(url):
                dead_writeups += 1
                continue
            if _keep(url):
                kept.append(w)
                alive_writeups += 1
            else:
                dead_writeups += 1
        m["writeups"] = kept

    # Filtrar skill_links
    alive_skills = 0
    dead_skills = 0
    for m in machines:
        kept_s: list[dict] = []
        for s in m.get("skill_links", []):
            url = s.get("url", "")
            if not _skill_domain_ok(url):
                dead_skills += 1
                continue
            if _keep(url):
                kept_s.append(s)
                alive_skills += 1
            else:
                dead_skills += 1
        m["skill_links"] = kept_s

    return machines, {
        "alive_writeups": alive_writeups,
        "dead_writeups": dead_writeups,
        "alive_skills": alive_skills,
        "dead_skills": dead_skills,
        "soft": soft,
    }


def main() -> int:
    if not MACHINES_FILE.exists():
        print(f"[validate] {MACHINES_FILE} no existe", file=sys.stderr)
        return 1

    machines = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    machines, stats = validate(machines)

    MACHINES_FILE.write_text(
        json.dumps(machines, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[validate] writeups → vivos: {stats['alive_writeups']} · "
        f"descartados: {stats['dead_writeups']}"
    )
    print(
        f"[validate] skills   → vivos: {stats['alive_skills']} · "
        f"descartados: {stats['dead_skills']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
