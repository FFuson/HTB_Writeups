"""One-shot: parsea `docs/glosario.mdx` (ES) y `docs/en/glossary.mdx` (EN) a
`data/glossary.json`, la nueva fuente de verdad del glosario táctico, para
generar UNA PÁGINA POR TÉRMINO (mejor SEO + citabilidad por LLMs/GEO).

NO forma parte del pipeline semanal: se ejecuta a mano cuando cambie el MDX
fuente. Diseño de CERO PÉRDIDA: además de los campos estructurados (emoji +
etiqueta + texto), guarda el cuerpo crudo (`body_raw`) de cada término, de modo
que los términos atípicos (sin los 5 emojis, con etiquetas custom o que son
referencias cruzadas) se rendericen igual sin perder contenido.

El glosario usa SIEMPRE los mismos 5 emojis como delimitadores de campo
(🎯🔗📡⚠️🛡️) pero las ETIQUETAS varían entre términos ("Remediación" vs
"Best practice", "Kill chain" vs "Uso"…), así que detectamos cualquier
`<emoji> **Etiqueta** — texto` y preservamos la etiqueta literal.

Uso:
    python -m scripts.parse_glossary            # escribe data/glossary.json
    python -m scripts.parse_glossary --check    # solo valida, no escribe
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "glossary.json"

# El glosario ya no vive en docs/ (se sirve como páginas generadas por
# generate_mdx desde glossary.json). Sus MDX fuente se archivan en
# data/glossary_src/ para poder re-parsear o editar la prosa con comodidad;
# glossary.json es el derivado que consume el generador.
SRC_DIR = ROOT / "data" / "glossary_src"
ES_SRC = SRC_DIR / "glosario.mdx"
EN_SRC = SRC_DIR / "glossary.mdx"

# Cabeceras `##` que NO son categorías de términos (preámbulo).
SKIP_BLOCKS = {
    "cómo leer este glosario",
    "como leer este glosario",
    "índice por bloque",
    "indice por bloque",
    "how to read this glossary",
    "index by block",
}

# emoji (+ variation selector opcional) + **Etiqueta** — texto
_EMOJI = r"[\U0001F000-\U0001FAFF←-➿⬀-⯿]"
FIELD_RE = re.compile(rf"^({_EMOJI}️?)\s+\*\*(.+?)\*\*\s*[—–\-]\s*(.*)$")

# emoji canónico (sin variation selector) → campo interno
CANON = {
    "🎯": "trinchera",
    "🔗": "kill_chain",
    "📡": "huella_defensiva",
    "⚠": "falso_amigo",
    "🛡": "remediacion",
}
CANON_FIELDS = set(CANON.values())


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ñ", "n")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "term"


def _emoji_base(emoji: str) -> str:
    return emoji.replace("️", "")


def _first_sentence(text: str) -> str:
    """Respuesta directa para meta-description y JSON-LD: primera frase del
    primer campo, limpia de markdown."""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"`([^`]*)`", r"\1", t)               # inline code
    t = re.sub(r"\*\*([^*]*)\*\*", r"\1", t)          # bold
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)    # links → texto
    m = re.search(r"(.+?[.!?])(\s|$)", t)
    return (m.group(1) if m else t)[:300].strip()


def _parse_fields(body_lines: list[str]) -> list[dict]:
    """Trocea el cuerpo de un término en campos {emoji, label, canon, text}."""
    fields: list[dict] = []
    cur: dict | None = None
    for line in body_lines:
        m = FIELD_RE.match(line.strip())
        if m:
            if cur:
                fields.append(cur)
            emoji, label, first = m.group(1), m.group(2).strip(), m.group(3)
            cur = {"emoji": emoji, "label": label,
                   "canon": CANON.get(_emoji_base(emoji)), "lines": [first]}
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        fields.append(cur)
    out = []
    for f in fields:
        out.append({
            "emoji": f["emoji"],
            "label": f["label"],
            "canon": f["canon"],
            "text": "\n".join(f["lines"]).strip(),
        })
    return out


def parse_glossary(path: Path) -> dict:
    if not path.exists():
        return {"blocks": [], "terms": []}
    lines = path.read_text(encoding="utf-8").splitlines()

    blocks: list[dict] = []
    terms: list[dict] = []
    seen_slugs: set[str] = set()

    cur_block: dict | None = None
    in_special = False
    cur_term: dict | None = None
    cur_lines: list[str] = []

    def close_term() -> None:
        nonlocal cur_term, cur_lines
        if not cur_term:
            return
        body = cur_lines[:]
        while body and body[-1].strip() in ("", "---"):
            body.pop()
        body_raw = "\n".join(body).strip()
        fields = _parse_fields(body)
        canons = {f["canon"] for f in fields if f["canon"]}
        if fields:
            answer = _first_sentence(fields[0]["text"])
        else:
            answer = _first_sentence(body_raw)
        cur_term.update({
            "fields": fields,
            "body_raw": body_raw,
            "answer": answer,
            "complete": canons == CANON_FIELDS,
        })
        terms.append(cur_term)
        cur_term = None
        cur_lines = []

    for raw in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", raw)
        h3 = re.match(r"^###\s+(.+?)\s*$", raw)
        if h2:
            close_term()
            name = h2.group(1).strip()
            if name.lower() in SKIP_BLOCKS:
                in_special, cur_block = True, None
            else:
                in_special = False
                bid = slugify(name)
                # Fusiona secciones `##` homónimas (p.ej. "WAF Evasion"
                # aparece dos veces) en un único bloque para no duplicar
                # grupos en la navegación.
                existing = next((b for b in blocks if b["id"] == bid), None)
                if existing:
                    cur_block = existing
                else:
                    cur_block = {"id": bid, "name": name}
                    blocks.append(cur_block)
            continue
        if h3 and not in_special and cur_block:
            close_term()
            name = h3.group(1).strip()
            slug = base = slugify(name)
            i = 2
            while slug in seen_slugs:
                slug, i = f"{base}-{i}", i + 1
            seen_slugs.add(slug)
            cur_term = {"slug": slug, "name": name, "block": cur_block["id"]}
            cur_lines = []
            continue
        if cur_term is not None:
            cur_lines.append(raw)
    close_term()

    return {"blocks": blocks, "terms": terms}


def _report(label: str, g: dict) -> None:
    n = len(g["terms"])
    complete = sum(1 for t in g["terms"] if t["complete"])
    nofields = [t["name"] for t in g["terms"] if not t["fields"]]
    print(f"[{label}] {len(g['blocks'])} bloques · {n} términos · "
          f"{complete} completos · {n - complete} con desviaciones")
    if nofields:
        print(f"     sin campos estructurados ({len(nofields)}): "
              f"{', '.join(nofields)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parsea el glosario MDX → JSON")
    ap.add_argument("--check", action="store_true", help="valida sin escribir")
    args = ap.parse_args(argv)

    data = {"es": parse_glossary(ES_SRC), "en": parse_glossary(EN_SRC)}
    _report("ES", data["es"])
    _report("EN", data["en"])

    # Guard: nunca vaciar glossary.json si faltan los MDX fuente (p.ej. si se
    # re-ejecuta tras moverlos). glossary.json es la fuente de verdad.
    if not data["es"]["terms"] and not data["en"]["terms"]:
        print(
            f"[parse_glossary] ⚠ 0 términos — ¿faltan los MDX fuente en "
            f"{SRC_DIR.relative_to(ROOT)}? NO sobreescribo glossary.json.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print("[parse_glossary] --check: no se escribe nada")
        return 0

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parse_glossary] escrito {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
