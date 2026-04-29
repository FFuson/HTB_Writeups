"""Fase 1: catálogo de máquinas retiradas.

Estrategias en orden de preferencia. La primera que funcione gana, las
demás aportan datos faltantes vía merge por nombre:

    1. HTB API v4 (requiere `HTB_API_TOKEN`).
    2. Dataset comunitario de htbmachines.github.io (S4vitar et al.).
    3. Seed local en `data/seed_machines.json`.

Salida: `data/machines.json` con un array de objetos normalizados.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from typing import Iterable

import requests

from scripts.config import (
    MACHINES_FILE,
    SEED_FILE,
    USER_AGENT,
    HTTP_TIMEOUT,
    normalize_difficulty,
    normalize_os,
)

HTB_API_URL = "https://labs.hackthebox.com/api/v4/machine/list/retired/paginated"
# Mantenido por el equipo de S4vitar; última actualización 2022-12, así
# que cubre ~201 máquinas pre-2023. Las posteriores las traerá la API.
HTBMACHINES_RAW = (
    "https://raw.githubusercontent.com/htbmachines/"
    "htbmachines.github.io/main/src/components/Dataset.jsx"
)


# ---------------------------------------------------------------------------
# Estrategia 1: HTB API oficial
# ---------------------------------------------------------------------------

def fetch_from_htb_api(token: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    machines: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            HTB_API_URL,
            headers=headers,
            params={"page": page, "per_page": 100},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("data") or payload.get("info") or []
        if not items:
            break
        machines.extend(_normalize_htb_api(m) for m in items)
        next_page = payload.get("links", {}).get("next") or payload.get("next_page_url")
        if not next_page:
            break
        page += 1
    return machines


def _normalize_htb_api(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "name": (raw.get("name") or "").strip(),
        "os": normalize_os(raw.get("os") or ""),
        "difficulty": normalize_difficulty(raw.get("difficultyText") or ""),
        "release_date": (raw.get("release") or "")[:10],
        "ip": raw.get("ip") or "",
        "points": raw.get("points"),
        "skills": "",
        "writeups": [],
    }


# ---------------------------------------------------------------------------
# Estrategia 2: HTBMachines (S4vitar)
# ---------------------------------------------------------------------------

def fetch_from_htbmachines() -> list[dict]:
    resp = requests.get(
        HTBMACHINES_RAW,
        headers={"User-Agent": USER_AGENT},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_htbmachines_js(resp.text)


def _extract_balanced(source: str, start: int) -> tuple[str, int]:
    """Devuelve la subcadena que abre con `{` en `start`, balanceando
    llaves y respetando strings con `'` o `"` y escapes.

    Retorna (cuerpo_incluyendo_llaves, posición_después_del_cierre).
    """
    if source[start] != "{":
        raise ValueError(f"se esperaba '{{' en posición {start}")
    depth = 0
    in_str = False
    str_char = ""
    escaped = False
    for i in range(start, len(source)):
        ch = source[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == str_char:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            str_char = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1], i + 1
    raise ValueError("desbalanceado")


def _extract_dataset_objects(js: str) -> list[str]:
    """Extrae todos los `{...}` de Dataset.jsx (literal inicial + pushes)."""
    objects: list[str] = []

    # 1) Array literal inicial: `const Dataset = [ {...}, {...}, ... ]`
    m = re.search(r"\bDataset\s*=\s*\[", js)
    if m:
        i = m.end()
        # Recorre el array añadiendo cada `{...}` hasta encontrar `]`
        while i < len(js):
            while i < len(js) and js[i] in " \t\r\n,":
                i += 1
            if i >= len(js) or js[i] == "]":
                break
            if js[i] == "{":
                obj, i = _extract_balanced(js, i)
                objects.append(obj)
            else:
                i += 1

    # 2) Llamadas posteriores: `Dataset.push({...})`
    for m in re.finditer(r"\bDataset\.push\s*\(\s*", js):
        i = m.end()
        if i < len(js) and js[i] == "{":
            obj, _ = _extract_balanced(js, i)
            objects.append(obj)

    return objects


_JS_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_KEY_RE = re.compile(r"([{,\s])([A-Za-z_][A-Za-z0-9_]*)\s*:")
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_FN_CALL_PATTERNS = [
    (re.compile(r"\bcount\s*\(\s*\)"), "null"),
    (re.compile(r"\bcrypto\.randomUUID\s*\(\s*\)"), '""'),
]


def _apply_outside_strings(s: str, transform) -> str:
    """Aplica `transform(text)` sólo a las regiones de `s` que no están
    dentro de strings JS con `"..."`. Las strings se conservan intactas.
    """
    out: list[str] = []
    last = 0
    for m in _JS_STRING_RE.finditer(s):
        out.append(transform(s[last : m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(transform(s[last:]))
    return "".join(out)


def _js_object_to_json(obj: str) -> str:
    """Convierte un objeto literal de JS a JSON válido. Todas las
    transformaciones que dependen de no estar dentro de strings se
    aplican vía `_apply_outside_strings`.
    """
    def strip_comments_and_calls(text: str) -> str:
        text = _LINE_COMMENT_RE.sub("", text)
        text = _BLOCK_COMMENT_RE.sub("", text)
        for pat, repl in _FN_CALL_PATTERNS:
            text = pat.sub(repl, text)
        return text

    def quote_keys_and_strip_trailing(text: str) -> str:
        text = _KEY_RE.sub(r'\1"\2":', text)
        text = _TRAILING_COMMA_RE.sub(r"\1", text)
        return text

    s = _apply_outside_strings(obj, strip_comments_and_calls)
    s = _apply_outside_strings(s, quote_keys_and_strip_trailing)
    return s


def _parse_htbmachines_js(js: str) -> list[dict]:
    objects = _extract_dataset_objects(js)
    if not objects:
        print("[fetch] htbmachines: no se encontraron objetos en Dataset", file=sys.stderr)
        return []

    machines: list[dict] = []
    failed = 0
    for raw in objects:
        try:
            obj = json.loads(_js_object_to_json(raw))
        except json.JSONDecodeError:
            failed += 1
            continue
        if isinstance(obj, dict):
            machines.append(_normalize_htbmachines(obj))
    if failed:
        print(f"[fetch] htbmachines: {failed} objetos no parseables", file=sys.stderr)
    return machines


def _normalize_htbmachines(raw: dict) -> dict:
    writeups: list[dict] = []
    if raw.get("youtube"):
        writeups.append({
            "autor": "S4vitar",
            "idioma": "ES",
            "formato": "Vídeo",
            "url": raw["youtube"],
        })
    # El campo `writeup` de htbmachines no identifica al autor: puede ser
    # Medium, GitHub o un blog cualquiera. Lo ignoramos para no
    # contaminar la lista blanca.
    skills = raw.get("skills") or raw.get("tecnicas") or ""
    skills = html.unescape(skills).strip()
    return {
        "id": raw.get("id"),
        "name": (raw.get("name") or "").strip(),
        "os": normalize_os(raw.get("so") or raw.get("os") or ""),
        "difficulty": normalize_difficulty(
            raw.get("dificultad") or raw.get("difficulty") or ""
        ),
        "release_date": (raw.get("fecha") or raw.get("release") or "")[:10],
        "ip": raw.get("ip") or "",
        "skills": skills,
        "writeups": writeups,
    }


# ---------------------------------------------------------------------------
# Estrategia 3: seed local
# ---------------------------------------------------------------------------

def load_seed() -> list[dict]:
    if not SEED_FILE.exists():
        return []
    raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return [_normalize_seed(m) for m in raw]


def _normalize_seed(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "name": raw["name"].strip(),
        "os": normalize_os(raw.get("os") or ""),
        "difficulty": normalize_difficulty(raw.get("difficulty") or ""),
        "release_date": raw.get("release_date") or "",
        "ip": raw.get("ip") or "",
        "skills": raw.get("skills") or "",
        "writeups": list(raw.get("writeups") or []),
    }


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge(*sources: Iterable[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for source in sources:
        for machine in source:
            name = (machine.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = dict(machine)
                continue
            # Combinar writeups sin duplicar URLs
            seen_urls = {w["url"] for w in existing.get("writeups", [])}
            for w in machine.get("writeups", []):
                if w.get("url") and w["url"] not in seen_urls:
                    existing.setdefault("writeups", []).append(w)
                    seen_urls.add(w["url"])
            # Rellenar campos que estuvieran vacíos
            for field in ("id", "os", "difficulty", "release_date", "ip", "skills", "points"):
                if not existing.get(field) and machine.get(field):
                    existing[field] = machine[field]
    return sorted(by_key.values(), key=lambda m: m["name"].lower())


def main() -> int:
    sources: list[list[dict]] = []

    token = os.environ.get("HTB_API_TOKEN")
    if token:
        try:
            api = fetch_from_htb_api(token)
            print(f"[fetch] HTB API: {len(api)} máquinas")
            sources.append(api)
        except Exception as exc:  # noqa: BLE001
            print(f"[fetch] HTB API falló: {exc}", file=sys.stderr)
    else:
        print("[fetch] HTB_API_TOKEN no definido, salto API oficial")

    try:
        htbm = fetch_from_htbmachines()
        print(f"[fetch] HTBMachines: {len(htbm)} máquinas")
        sources.append(htbm)
    except Exception as exc:  # noqa: BLE001
        print(f"[fetch] HTBMachines falló: {exc}", file=sys.stderr)

    seed = load_seed()
    if seed:
        print(f"[fetch] Seed local: {len(seed)} máquinas")
        sources.append(seed)

    machines = merge(*sources)
    if not machines:
        print("[fetch] ERROR: ninguna fuente devolvió datos", file=sys.stderr)
        return 1

    MACHINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    MACHINES_FILE.write_text(
        json.dumps(machines, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[fetch] Guardadas {len(machines)} máquinas en {MACHINES_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
