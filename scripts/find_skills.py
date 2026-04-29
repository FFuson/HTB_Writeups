"""Fase 2.5: vincula el campo `skills` de cada máquina con recursos
de un glosario curado (HackTricks, GTFOBins, PortSwigger, etc.).

Salida: cada máquina gana un campo `skill_links` con esta forma:

    [
      {
        "skill": "Kerberoasting",
        "fuente": "HackTricks",
        "url": "https://book.hacktricks.wiki/.../kerberoast.html"
      },
      ...
    ]

El `validate_links.py` luego se encarga de purgar enlaces muertos.
"""

from __future__ import annotations

import json
import re
import sys

from scripts.config import MACHINES_FILE, SKILLS_GLOSSARY


def _load_glossary() -> dict[str, dict]:
    if not SKILLS_GLOSSARY.exists():
        print(f"[skills] {SKILLS_GLOSSARY} no existe", file=sys.stderr)
        return {}
    raw = json.loads(SKILLS_GLOSSARY.read_text(encoding="utf-8"))
    return raw.get("skills", {})


def _normalize(text: str) -> str:
    """Limpia un token para matching: minúsculas, sin acentos, espacios."""
    text = text.lower().strip()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text)


def _build_alias_index(glossary: dict[str, dict]) -> list[tuple[str, str]]:
    """Lista de tuplas (alias_normalizado, skill_id) ordenada por longitud
    de alias descendente, para que matches más específicos ganen primero
    (e.g. `as-rep roasting` antes que `as`).
    """
    pairs: list[tuple[str, str]] = []
    for skill_id, entry in glossary.items():
        for alias in entry.get("aliases", []):
            pairs.append((_normalize(alias), skill_id))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def find_skill_links(skills_text: str, glossary: dict[str, dict],
                     alias_index: list[tuple[str, str]]) -> list[dict]:
    """Recorre `skills_text` y devuelve una lista de recursos asociados a
    cada skill detectada. Sin duplicar URLs.
    """
    if not skills_text or not skills_text.strip():
        return []

    haystack = _normalize(skills_text)
    matched_ids: list[str] = []
    seen: set[str] = set()
    for alias, skill_id in alias_index:
        if alias in haystack and skill_id not in seen:
            matched_ids.append(skill_id)
            seen.add(skill_id)

    links: list[dict] = []
    seen_urls: set[str] = set()
    for skill_id in matched_ids:
        entry = glossary.get(skill_id, {})
        nombre = entry.get("nombre", skill_id)
        nombre_en = entry.get("nombre_en", nombre)
        for recurso in entry.get("recursos", []):
            url = recurso.get("url")
            if not url or url in seen_urls:
                continue
            links.append({
                "skill": nombre,
                "skill_en": nombre_en,
                "fuente": recurso.get("fuente", "—"),
                "url": url,
            })
            seen_urls.add(url)
    return links


def augment(machines: list[dict]) -> tuple[list[dict], int]:
    glossary = _load_glossary()
    alias_index = _build_alias_index(glossary)

    total = 0
    for m in machines:
        links = find_skill_links(m.get("skills", ""), glossary, alias_index)
        m["skill_links"] = links
        total += len(links)
    return machines, total


# Stop-words que aparecen mucho pero no son técnicas reales.
_NOISE_TOKENS = {
    "abusing", "abuse", "and", "as", "at", "attack", "based", "by", "bypass",
    "bypassing", "configuration", "credentials", "default", "directory",
    "enumeration", "error", "exploit", "exploitation", "file", "files", "for",
    "from", "function", "functions", "group", "in", "index", "information",
    "injection", "injections", "is", "leakage", "method", "methods", "modify",
    "modifying", "not", "of", "on", "open", "or", "package", "path", "paths",
    "permissions", "privileges", "remote", "right", "script", "scripts",
    "service", "services", "session", "sessions", "system", "the", "to",
    "tool", "tools", "type", "user", "users", "using", "via", "vulnerability",
    "with", "without", "write", "writeable", "writeable",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def mine_unmapped_skills(
    machines: list[dict], glossary: dict[str, dict], top_n: int = 20
) -> list[tuple[str, int]]:
    """Devuelve los `top_n` tokens más frecuentes en `skills` que NO
    están cubiertos por ningún alias del glosario.

    Útil para detectar skills nuevas que merecen entrada propia.
    """
    aliases_norm = {
        _normalize(alias)
        for entry in glossary.values()
        for alias in entry.get("aliases", [])
    }
    counts: dict[str, int] = {}
    for m in machines:
        text = (m.get("skills") or "").lower()
        for tok in _TOKEN_RE.findall(text):
            tok_n = _normalize(tok)
            if tok_n in _NOISE_TOKENS or len(tok_n) < 4:
                continue
            if any(tok_n in alias for alias in aliases_norm):
                continue
            counts[tok_n] = counts.get(tok_n, 0) + 1

    return sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]


def main() -> int:
    if not MACHINES_FILE.exists():
        print(
            f"[skills] {MACHINES_FILE} no existe. Ejecuta antes fetch_machines.",
            file=sys.stderr,
        )
        return 1

    machines = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    machines, total = augment(machines)

    MACHINES_FILE.write_text(
        json.dumps(machines, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    matched_machines = sum(1 for m in machines if m.get("skill_links"))
    print(
        f"[skills] {matched_machines}/{len(machines)} máquinas con recursos · "
        f"{total} enlaces totales"
    )

    # Skill miner — detecta candidatas a nueva entrada del glosario.
    glossary = _load_glossary()
    candidates = mine_unmapped_skills(machines, glossary, top_n=10)
    if candidates:
        joined = ", ".join(f"{tok}({n})" for tok, n in candidates)
        print(
            f"[skills] ⚠ tokens frecuentes sin entrada en glosario: {joined}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
