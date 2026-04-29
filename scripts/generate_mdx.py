"""Fase 4: vuelca `machines.json` a archivos `.mdx` para Mintlify y
reescribe `docs/docs.json` con la navegación lateral.

La estructura de carpetas refleja la categorización:
    docs/machines/{linux,windows,otros}/{facil,medio,dificil,insano}/{slug}.mdx

Mintlify deriva el menú de la jerarquía declarada en `docs.json`. Como
escribir 200 entradas a mano sería un castigo, este script lo regenera
de cero leyendo el árbol que acaba de producir.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from scripts.config import (
    AUTHORS,
    DOCS_DIR,
    DOCS_JSON,
    MACHINES_DIR,
    MACHINES_FILE,
    difficulty_to_slug,
    os_to_slug,
)


# El orden marca la prioridad de visualización (idioma + autor)
PRIORITY = {
    ("ES", "S4vitar"): 0,
    ("ES", "El Pingüino de Mario"): 1,
    ("ES", "Securízame"): 2,
    ("EN", "0xdf"): 10,
    ("EN", "IppSec"): 11,
}

DIFFICULTY_ORDER = ["Fácil", "Medio", "Difícil", "Insano"]
OS_ORDER = ["Linux", "Windows", "Other"]
OS_LABEL = {"Linux": "Linux", "Windows": "Windows", "Other": "Otros"}
DIFFICULTY_LABEL = {
    "Fácil": "Fácil",
    "Medio": "Medio",
    "Difícil": "Difícil",
    "Insano": "Insano",
}


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[áàä]", "a", s)
    s = re.sub(r"[éèë]", "e", s)
    s = re.sub(r"[íìï]", "i", s)
    s = re.sub(r"[óòö]", "o", s)
    s = re.sub(r"[úùü]", "u", s)
    s = s.replace("ñ", "n")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "machine"


def _writeup_sort_key(w: dict) -> tuple[int, str, str]:
    """Sort estable y determinista: (prioridad, autor, url)."""
    return (
        PRIORITY.get((w.get("idioma", ""), w.get("autor", "")), 99),
        w.get("autor", ""),
        w.get("url", ""),
    )


def _format_writeup_row(w: dict) -> str:
    autor = w.get("autor", "Anónimo")
    idioma = w.get("idioma", "—")
    formato = w.get("formato", "—")
    url = w.get("url", "#")
    bandera = "🇪🇸" if idioma == "ES" else "🇬🇧" if idioma == "EN" else "🌐"
    return f"| {bandera} {idioma} | **{autor}** | {formato} | [Abrir]({url}) |"


def _yaml_string(value: str) -> str:
    """Devuelve `value` envuelto entre comillas dobles, escapado para YAML."""
    return json.dumps(value, ensure_ascii=False)


def render_machine(machine: dict) -> str:
    name = machine["name"]
    os_name = machine.get("os", "Other")
    difficulty = machine.get("difficulty", "Fácil")
    ip = machine.get("ip") or "—"
    release_date = machine.get("release_date") or "—"
    skills_raw = machine.get("skills") or ""

    writeups = sorted(machine.get("writeups", []), key=_writeup_sort_key)

    # Frontmatter
    fm_lines = [
        "---",
        f"title: {_yaml_string(name)}",
        f"description: {_yaml_string(f'Writeups verificados de la máquina {name} de Hack The Box')}",
        "---",
    ]
    front = "\n".join(fm_lines)

    # Tabla de metadatos
    meta_table = "\n".join([
        "| Campo | Valor |",
        "| --- | --- |",
        f"| Sistema operativo | {_mdx_safe(os_name)} |",
        f"| Dificultad | {_mdx_safe(difficulty)} |",
        f"| IP | `{_mdx_safe(ip)}` |",
        f"| Fecha de lanzamiento | {_mdx_safe(release_date)} |",
        f"| Skills | {_mdx_safe(skills_raw) if skills_raw else '—'} |",
    ])

    # Tabla de writeups
    if writeups:
        rows = "\n".join(_format_writeup_row(w) for w in writeups)
        wu_block = "\n".join([
            "## Writeups",
            "",
            "| Idioma | Autor | Formato | Enlace |",
            "| --- | --- | --- | --- |",
            rows,
        ])
    else:
        wu_block = (
            "## Writeups\n\n"
            "<Warning>Aún no hay writeups validados de autores en lista "
            "blanca para esta máquina. Vuelve a ejecutar el pipeline más "
            "tarde.</Warning>"
        )

    # Recursos por skill
    skill_links = machine.get("skill_links") or []
    if skill_links:
        skill_rows = "\n".join(
            f"| {_mdx_safe(s.get('skill', '—'))} | "
            f"{_mdx_safe(s.get('fuente', '—'))} | "
            f"[Abrir]({s.get('url', '#')}) |"
            for s in skill_links
        )
        skills_block = "\n".join([
            "## Recursos por skill",
            "",
            "Documentación curada para cada técnica que aparece en la "
            "columna *Skills* de arriba. Fuentes: HackTricks, GTFOBins, "
            "PortSwigger, etc.",
            "",
            "| Skill | Fuente | Enlace |",
            "| --- | --- | --- |",
            skill_rows,
        ])
    else:
        skills_block = ""

    sections = [front, f"# {name}", meta_table, wu_block]
    if skills_block:
        sections.append(skills_block)
    return "\n\n".join(sections) + "\n"


def write_machine_file(machine: dict) -> Path:
    os_slug = os_to_slug(machine.get("os", "Other"))
    diff_slug = difficulty_to_slug(machine.get("difficulty", "Fácil"))
    slug = slugify(machine["name"])

    target_dir = MACHINES_DIR / os_slug / diff_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.mdx"
    target.write_text(render_machine(machine), encoding="utf-8")
    return target


def _machine_page_path(machine: dict) -> str:
    """Ruta del slug usada por Mintlify (sin extensión, sin / inicial)."""
    return (
        f"machines/{os_to_slug(machine.get('os', 'Other'))}/"
        f"{difficulty_to_slug(machine.get('difficulty', 'Fácil'))}/"
        f"{slugify(machine['name'])}"
    )


def _mdx_safe(text: str) -> str:
    """Escapa caracteres que MDX interpreta como JSX/expresiones.

    MDX trata `<`, `>`, `{`, `}` como apertura de tags o expresiones
    JS. En contenido textual hay que neutralizarlos. `|` también, para
    que no rompa columnas de tabla.
    """
    if not text:
        return "—"
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("|", "\\|")
    )


def _truncate(text: str, limit: int = 70) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return _mdx_safe(text)


def _difficulty_badge(diff: str) -> str:
    """Pinta la dificultad con un emoji para escaneo visual rápido."""
    return {
        "Fácil": "🟢 Fácil",
        "Medio": "🟡 Medio",
        "Difícil": "🟠 Difícil",
        "Insano": "🔴 Insano",
    }.get(diff, diff)


def _skill_chips(machine: dict, raw_skills_fallback: int = 80) -> str:
    """Si la máquina tiene skills detectadas en `skill_links`, las
    muestra como chips legibles (sin duplicar). Si no, cae al texto
    crudo truncado.
    """
    seen: list[str] = []
    for s in machine.get("skill_links", []):
        name = s.get("skill", "").strip()
        if name and name not in seen:
            seen.append(name)
    if seen:
        chips = " · ".join(_mdx_safe(s) for s in seen)
        return chips
    return _truncate(machine.get("skills", ""), raw_skills_fallback)


def render_index(machines: list[dict]) -> str:
    """Genera `all.mdx`: tabla maestra de TODAS las máquinas, agrupada
    por SO. Pensada para usar con `Cmd+K` y para tener una vista única
    de todo el catálogo.
    """
    fm = "\n".join([
        "---",
        'title: "Todas las máquinas"',
        'description: "Tabla maestra del catálogo completo de máquinas retiradas"',
        "---",
    ])

    by_os: dict[str, list[dict]] = {}
    for m in machines:
        os_name = m.get("os") or "Other"
        if os_name not in OS_ORDER:
            os_name = "Other"
        by_os.setdefault(os_name, []).append(m)

    intro = (
        f"Catálogo completo: **{len(machines)} máquinas retiradas** "
        f"con {sum(len(m.get('writeups', [])) for m in machines)} writeups "
        f"validados. Usa <kbd>Cmd</kbd>+<kbd>K</kbd> (o "
        "<kbd>Ctrl</kbd>+<kbd>K</kbd>) para buscar por nombre o skill."
    )

    sections: list[str] = [fm, "# Todas las máquinas", intro]

    for os_name in OS_ORDER:
        ms = sorted(
            by_os.get(os_name, []),
            key=lambda m: (m.get("name", "").lower()),
        )
        if not ms:
            continue
        rows = []
        for m in ms:
            name = _mdx_safe(m["name"])
            page = _machine_page_path(m)
            n_writeups = len(m.get("writeups", []))
            rows.append(
                f"| [{name}](/{page}) "
                f"| {_difficulty_badge(m.get('difficulty', '—'))} "
                f"| {_skill_chips(m)} "
                f"| {n_writeups} |"
            )
        section = "\n".join([
            f"## {OS_LABEL[os_name]} ({len(ms)})",
            "",
            "| Máquina | Dificultad | Skills | Writeups |",
            "| --- | --- | --- | ---: |",
            *rows,
        ])
        sections.append(section)

    return "\n\n".join(sections) + "\n"


def write_index_file(machines: list[dict]) -> Path:
    target = DOCS_DIR / "all.mdx"
    target.write_text(render_index(machines), encoding="utf-8")
    return target


_STATS_BLOCK_RE = re.compile(
    r"\{/\* STATS:START \*/\}.*?\{/\* STATS:END \*/\}",
    re.DOTALL,
)


def _render_stats_block(machines: list[dict]) -> str:
    """Bloque de tarjetas con cifras del catálogo. Mintlify lo
    renderiza con CardGroup."""
    n_machines = len(machines)
    n_writeups = sum(len(m.get("writeups", [])) for m in machines)
    n_skill_links = sum(len(m.get("skill_links", [])) for m in machines)
    by_os: dict[str, int] = {}
    for m in machines:
        by_os[m.get("os") or "Other"] = by_os.get(m.get("os") or "Other", 0) + 1
    os_summary = " · ".join(
        f"{n} {OS_LABEL.get(os_name, os_name)}"
        for os_name, n in sorted(by_os.items(), key=lambda x: -x[1])
    )
    body = "\n".join([
        '<CardGroup cols={3}>',
        f'  <Card title="{n_machines} máquinas" icon="server">',
        f'    {os_summary}',
        '  </Card>',
        f'  <Card title="{n_writeups} writeups" icon="link">',
        '    Validados con HEAD periódico',
        '  </Card>',
        f'  <Card title="{n_skill_links} recursos" icon="graduation-cap">',
        '    HackTricks, GTFOBins, PortSwigger, etc.',
        '  </Card>',
        '</CardGroup>',
    ])
    return f"{{/* STATS:START */}}\n{body}\n{{/* STATS:END */}}"


def write_intro_stats(machines: list[dict]) -> None:
    """Reescribe lo que haya entre `STATS:START` y `STATS:END` en
    `introduction.mdx`. Si los marcadores no existen, no toca nada.
    """
    intro = DOCS_DIR / "introduction.mdx"
    if not intro.exists():
        return
    text = intro.read_text(encoding="utf-8")
    new_text, count = _STATS_BLOCK_RE.subn(_render_stats_block(machines), text)
    if count:
        intro.write_text(new_text, encoding="utf-8")


def reset_machines_dir() -> None:
    """Vacía `docs/machines/` antes de regenerar para evitar quedarnos
    con archivos huérfanos de máquinas que ya no procesamos."""
    if MACHINES_DIR.exists():
        shutil.rmtree(MACHINES_DIR)
    MACHINES_DIR.mkdir(parents=True, exist_ok=True)


def build_navigation(machines: list[dict]) -> list[dict]:
    """Construye el bloque `tabs` de Mintlify a partir del árbol generado."""
    by_os: dict[str, dict[str, list[str]]] = {}

    for m in machines:
        os_name = m.get("os") or "Other"
        if os_name not in OS_ORDER:
            os_name = "Other"
        diff = m.get("difficulty") or "Fácil"
        os_slug = os_to_slug(os_name)
        diff_slug = difficulty_to_slug(diff)
        slug = slugify(m["name"])
        page = f"machines/{os_slug}/{diff_slug}/{slug}"
        by_os.setdefault(os_name, {}).setdefault(diff, []).append(page)

    tabs = [
        {
            "tab": "Inicio",
            "groups": [
                {
                    "group": "Bienvenida",
                    "pages": ["introduction", "como-usar", "creditos"],
                },
                {
                    "group": "Catálogo",
                    "pages": ["all"],
                },
            ],
        }
    ]

    for os_name in OS_ORDER:
        if os_name not in by_os:
            continue
        groups = []
        for diff in DIFFICULTY_ORDER:
            pages = sorted(by_os[os_name].get(diff, []))
            if not pages:
                continue
            groups.append({
                "group": DIFFICULTY_LABEL[diff],
                "pages": pages,
            })
        if not groups:
            continue
        tabs.append({"tab": OS_LABEL[os_name], "groups": groups})

    return tabs


def write_docs_json(machines: list[dict]) -> None:
    base = {
        "$schema": "https://mintlify.com/docs.json",
        "theme": "mint",
        "name": "HTB Writeups Hub",
        "description": "Directorio curado de writeups de máquinas retiradas de Hack The Box",
        "colors": {
            "primary": "#9FEF00",
            "light": "#9FEF00",
            "dark": "#111927",
        },
        "navigation": {"tabs": build_navigation(machines)},
        "footerSocials": {
            "github": "https://github.com/quodix",
        },
    }
    DOCS_JSON.write_text(
        json.dumps(base, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    if not MACHINES_FILE.exists():
        print(f"[mdx] {MACHINES_FILE} no existe", file=sys.stderr)
        return 1

    machines = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    if not machines:
        print("[mdx] machines.json está vacío", file=sys.stderr)
        return 1

    reset_machines_dir()
    for m in machines:
        write_machine_file(m)

    write_index_file(machines)
    write_intro_stats(machines)
    write_docs_json(machines)

    # Sanity: imprime la cuenta por OS/dificultad
    counts: dict[str, dict[str, int]] = {}
    for m in machines:
        os_name = m.get("os") or "Other"
        diff = m.get("difficulty") or "Fácil"
        counts.setdefault(os_name, {}).setdefault(diff, 0)
        counts[os_name][diff] += 1

    print(f"[mdx] {len(machines)} páginas generadas en {MACHINES_DIR}")
    for os_name, by_diff in counts.items():
        breakdown = ", ".join(f"{d}: {n}" for d, n in by_diff.items())
        print(f"[mdx]   {os_name}: {breakdown}")
    print(f"[mdx] docs.json reescrito en {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
