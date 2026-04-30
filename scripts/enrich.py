"""Fase 4.5: enriquecimiento del catálogo.

Para cada máquina, calcula y persiste:

  - `primary_vector`  — etiqueta cerrada (web/ad/linux-privesc/...).
  - `cves`            — lista de CVEs / MS-XX detectados en el campo skills.
  - `duration_min`    — duración (minutos) del vídeo de IppSec, scrapeada
                        de YouTube y cacheada con TTL de 30 días.

No usa API keys. Si el scraping falla, deja los campos vacíos sin
romper el resto del pipeline.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import requests

from scripts.cache import JsonCache
from scripts.config import HTTP_TIMEOUT, MACHINES_FILE


# ---------------------------------------------------------------------------
# 1. Vector primario — heurística sobre el campo `skills`
# ---------------------------------------------------------------------------

# Patrones por categoría. Orden: el primero que matchee gana. La cola lleva
# los más genéricos. Las claves son los identificadores de chips.
_VECTOR_RULES: list[tuple[str, list[str]]] = [
    ("ad", [
        r"\bactive\s*directory\b", r"\bkerberoast", r"\bas[-_ ]?rep",
        r"\bdcsync\b", r"\bbloodhound\b", r"\bgpp\b", r"\bntds\b",
        r"\bdomain\s*controller\b", r"\bgolden\s*ticket\b",
        r"\bsilver\s*ticket\b", r"\bldap\b", r"\bdelegation\b",
        r"\bgetnpusers\b",
    ]),
    ("binary-exploitation", [
        r"\bbuffer\s*overflow\b", r"\bstack\s*overflow\b",
        r"\brop\s*chain\b", r"\bret2\w+\b", r"\bshellcode\b",
        r"\bformat\s*string\b", r"\breverse\s*engineering\b",
        r"\bbinary\s*exploitation\b", r"\bgdb\b",
        r"\b(use[-_ ]?after[-_ ]?free|uaf)\b",
    ]),
    ("crypto", [
        r"\b(rsa|aes|des|3des|chacha|salsa20)\b", r"\bcipher\b",
        r"\bvigen[èe]re\b", r"\bxor\s*cipher\b", r"\bhash\s*length\s*ext",
        r"\bpadding\s*oracle\b", r"\bjwt\s*forgery\b",
    ]),
    ("forensics", [
        r"\bforensic", r"\bwireshark\b", r"\bpcap\b", r"\bvolatility\b",
        r"\busb\s*forensics\b", r"\bautopsy\b", r"\bfile\s*carving\b",
    ]),
    ("osint", [
        r"\bosint\b", r"\bgoogle\s*dorks\b", r"\bsubdomain\s*recon\b",
    ]),
    ("web", [
        r"\bsql\s*injection\b", r"\bsqli\b", r"\bxss\b", r"\bssrf\b",
        r"\bxxe\b", r"\bjwt\b", r"\bcsrf\b", r"\bdeserializ",
        r"\b(local|remote)\s*file\s*inclusion\b", r"\blfi\b",
        r"\brfi\b", r"\bsst[ie]\b", r"\bprototype\s*pollution\b",
        r"\bgraphql\b", r"\bnosql\s*injection\b", r"\bweb\s*shell\b",
        r"\bphpbash\b", r"\bwordpress\b", r"\bdrupal\b", r"\bjoomla\b",
        r"\bapache\s*tomcat\b", r"\bnodejs\b", r"\bfile\s*upload\b",
    ]),
]

# Si tras la heurística no encaja nada, el OS marca el fallback.
_OS_FALLBACK = {
    "Linux": "linux-privesc",
    "Windows": "windows-privesc",
    "Other": "other",
}


def detect_vector(skills: str, os_name: str) -> str:
    text = (skills or "").lower()
    for label, patterns in _VECTOR_RULES:
        for pat in patterns:
            if re.search(pat, text):
                return label
    return _OS_FALLBACK.get(os_name, "other")


# ---------------------------------------------------------------------------
# 2. CVEs y MS-bulletins — extracción regex
# ---------------------------------------------------------------------------

_CVE_RE = re.compile(r"\bCVE[-_]?(\d{4})[-_]?(\d{4,7})\b", re.IGNORECASE)
_MS_RE = re.compile(r"\bMS(\d{2})[-_]?(\d{3})\b", re.IGNORECASE)


def extract_cves(skills: str) -> list[dict]:
    """Devuelve lista de chips CVE/MS con {id, label, url}."""
    found: list[dict] = []
    seen: set[str] = set()
    for m in _CVE_RE.finditer(skills or ""):
        cid = f"CVE-{m.group(1)}-{m.group(2)}"
        if cid in seen:
            continue
        seen.add(cid)
        found.append({
            "id": cid,
            "label": cid,
            "url": f"https://nvd.nist.gov/vuln/detail/{cid}",
        })
    for m in _MS_RE.finditer(skills or ""):
        cid = f"MS{m.group(1)}-{m.group(2)}"
        if cid in seen:
            continue
        seen.add(cid)
        found.append({
            "id": cid,
            "label": cid,
            "url": (
                "https://learn.microsoft.com/en-us/security-updates/"
                f"securitybulletins/{2000 + int(m.group(1))}/{cid.lower()}"
            ),
        })
    return found


# ---------------------------------------------------------------------------
# 3. Duración del vídeo de IppSec (sin API key)
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r'"lengthSeconds":"(\d+)"')

_YT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_YT_COOKIES = {"SOCS": "CAI"}

_duration_cache = JsonCache("youtube_durations", ttl_days=30)


def _ippsec_video_id(machine: dict) -> str | None:
    """Extrae el videoId de IppSec si está en writeups."""
    for w in machine.get("writeups", []):
        if w.get("autor") != "IppSec":
            continue
        url = w.get("url", "")
        m = re.search(r"v=([A-Za-z0-9_-]{11})", url)
        if m:
            return m.group(1)
    return None


def _fetch_duration(video_id: str) -> int | None:
    """Devuelve duración en minutos (None si no se puede)."""
    cached = _duration_cache.get(video_id)
    if cached is not None:
        return cached if cached > 0 else None

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _YT_UA, "Accept-Language": "en-US,en;q=0.9"},
            cookies=_YT_COOKIES,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200 or "consent.youtube.com" in resp.url:
        return None

    m = _DURATION_RE.search(resp.text)
    if not m:
        return None
    seconds = int(m.group(1))
    minutes = max(1, round(seconds / 60))
    _duration_cache.set(video_id, minutes)
    return minutes


def resolve_durations(machines: list[dict], max_workers: int = 8) -> int:
    """Resuelve duración para todas las máquinas con vídeo de IppSec.
    Devuelve el número de duraciones obtenidas."""
    pairs: list[tuple[dict, str]] = []
    for m in machines:
        if m.get("duration_min"):
            continue
        vid = _ippsec_video_id(m)
        if vid:
            pairs.append((m, vid))

    if not pairs:
        return 0

    resolved = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_duration, vid): m for m, vid in pairs
        }
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                minutes = fut.result()
            except Exception:
                minutes = None
            if minutes:
                m["duration_min"] = minutes
                resolved += 1
    return resolved


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def enrich(machines: list[dict]) -> dict[str, int]:
    stats = {"vectors": 0, "cves": 0, "durations": 0}
    for m in machines:
        # Vector
        v = detect_vector(m.get("skills", ""), m.get("os", ""))
        if v:
            m["primary_vector"] = v
            stats["vectors"] += 1
        # CVEs
        cves = extract_cves(m.get("skills", ""))
        if cves:
            m["cves"] = cves
            stats["cves"] += len(cves)
    # Duraciones (red, en paralelo)
    stats["durations"] = resolve_durations(machines)
    _duration_cache.save()
    return stats


def main() -> int:
    if not MACHINES_FILE.exists():
        print(f"[enrich] {MACHINES_FILE} no existe", file=sys.stderr)
        return 1

    machines = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    stats = enrich(machines)
    MACHINES_FILE.write_text(
        json.dumps(machines, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[enrich] vectores: {stats['vectors']} · "
        f"CVEs: {stats['cves']} · "
        f"duraciones IppSec: {stats['durations']}"
    )
    # Distribución por vector como sanity check
    by_v: dict[str, int] = {}
    for m in machines:
        by_v[m.get("primary_vector", "—")] = by_v.get(m.get("primary_vector", "—"), 0) + 1
    breakdown = ", ".join(f"{v}={n}" for v, n in sorted(by_v.items(), key=lambda kv: -kv[1]))
    print(f"[enrich]   distribución: {breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
