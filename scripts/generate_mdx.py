"""Fase 4: vuelca `machines.json` a archivos `.mdx` para Mintlify y
reescribe `docs/docs.json` con la navegación lateral.

La estructura de carpetas refleja la categorización:
    docs/machines/{linux,windows,otros}/{facil,medio,dificil,insano}/{slug}.mdx

Mintlify deriva el menú de la jerarquía declarada en `docs.json`. Como
escribir 200 entradas a mano sería un castigo, este script lo regenera
de cero leyendo el árbol que acaba de producir.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

from scripts.config import (
    AUTHORS,
    DOCS_DIR,
    DOCS_JSON,
    LOCALES,
    MACHINES_DIR,
    MACHINES_FILE,
    difficulty_to_slug,
    os_to_slug,
)


# Idioma por defecto (raíz del sitio) y orden de los demás
DEFAULT_LANG = "es"
EXTRA_LANGS = ["en"]
ALL_LANGS = [DEFAULT_LANG, *EXTRA_LANGS]


def _docs_root(lang: str) -> Path:
    """ES (default) en raíz; el resto bajo docs/<lang>/."""
    return DOCS_DIR if lang == DEFAULT_LANG else DOCS_DIR / lang


def _machines_root(lang: str) -> Path:
    return _docs_root(lang) / "machines"


def _page_prefix(lang: str) -> str:
    """Prefijo para entradas de Mintlify y URLs internas."""
    return "" if lang == DEFAULT_LANG else f"{lang}/"


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


SITE_URL = "https://rootea.es"
BUILD_DATE = _dt.date.today().isoformat()


def _jsonld_block(payload: dict) -> str:
    """Renderiza un bloque <script type="application/ld+json"> con el
    payload serializado de forma compacta. Mintlify lo conserva al
    renderizar y los crawlers lo extraen del HTML.
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'<script type="application/ld+json">{body}</script>'


def _machine_jsonld(machine: dict, lang: str, url: str) -> dict:
    skills_keywords = ", ".join(
        s.get("skill", "")
        for s in machine.get("skill_links", [])
        if s.get("skill")
    )
    return {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": f"{machine['name']} — HTB Writeup Index",
        "name": machine["name"],
        "url": url,
        "inLanguage": lang,
        "datePublished": machine.get("release_date") or BUILD_DATE,
        "dateModified": BUILD_DATE,
        "about": {"@type": "Thing", "name": "Hack The Box (HTB)"},
        "keywords": skills_keywords or machine.get("skills", "")[:200],
        "isPartOf": {
            "@type": "WebSite",
            "name": "rootea.es",
            "url": SITE_URL,
        },
        "author": {"@type": "Organization", "name": "rootea.es"},
        "proficiencyLevel": machine.get("difficulty", ""),
    }


def _all_jsonld(machines: list[dict], lang: str, url: str) -> dict:
    items = [
        {
            "@type": "ListItem",
            "position": idx,
            "url": f"{SITE_URL}/{_machine_page_path(m, lang)}",
            "name": m["name"],
        }
        for idx, m in enumerate(
            sorted(machines, key=lambda m: m.get("name", "").lower()),
            start=1,
        )
    ]
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": LOCALES[lang]["ui"]["all_machines"],
        "url": url,
        "inLanguage": lang,
        "dateModified": BUILD_DATE,
        "isPartOf": {"@type": "WebSite", "name": "rootea.es", "url": SITE_URL},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(items),
            "itemListElement": items,
        },
    }


def _last_updated_line(lang: str) -> str:
    label = "Última actualización" if lang == "es" else "Last updated"
    return f"_{label}: {BUILD_DATE}_"


def _format_writeup_row_i18n(w: dict, t: dict) -> str:
    autor = w.get("autor", "Anónimo")
    idioma = w.get("idioma", "—")
    formato = w.get("formato", "—")
    url = w.get("url", "#")
    bandera = "🇪🇸" if idioma == "ES" else "🇬🇧" if idioma == "EN" else "🌐"
    return f"| {bandera} {idioma} | **{autor}** | {formato} | [{t['open']}]({url}) |"


def render_machine(machine: dict, lang: str = DEFAULT_LANG) -> str:
    loc = LOCALES[lang]
    t = loc["ui"]

    name = machine["name"]
    os_name_canon = machine.get("os", "Other")
    os_name = loc["os_label"].get(os_name_canon, os_name_canon)
    diff_canon = machine.get("difficulty", "Fácil")
    difficulty = loc["difficulty"].get(diff_canon, diff_canon)
    ip = machine.get("ip") or "—"
    release_date = machine.get("release_date") or "—"
    skills_raw = machine.get("skills") or ""

    writeups = sorted(machine.get("writeups", []), key=_writeup_sort_key)

    fm_lines = [
        "---",
        f"title: {_yaml_string(name)}",
        f"description: {_yaml_string(t['machine_page_desc'].format(name=name))}",
        "---",
    ]
    front = "\n".join(fm_lines)

    meta_table = "\n".join([
        "| · | · |",
        "| --- | --- |",
        f"| {t['system']} | {_mdx_safe(os_name)} |",
        f"| {t['difficulty']} | {_mdx_safe(difficulty)} |",
        f"| {t['ip']} | `{_mdx_safe(ip)}` |",
        f"| {t['retired']} | {_mdx_safe(release_date)} |",
        f"| {t['skills']} | {_mdx_safe(skills_raw) if skills_raw else '—'} |",
    ])

    if writeups:
        rows = "\n".join(_format_writeup_row_i18n(w, t) for w in writeups)
        wu_block = "\n".join([
            f"## {t['writeups']}",
            "",
            f"| {t['language']} | {t['author']} | {t['format']} | {t['link']} |",
            "| --- | --- | --- | --- |",
            rows,
        ])
    else:
        wu_block = f"## {t['writeups']}\n\n<Warning>{t['no_writeups_warn']}</Warning>"

    skill_links = machine.get("skill_links") or []
    if skill_links:
        skill_rows = "\n".join(
            f"| {_mdx_safe(_skill_label(s, lang))} | "
            f"{_mdx_safe(s.get('fuente', '—'))} | "
            f"[{t['open']}]({s.get('url', '#')}) |"
            for s in skill_links
        )
        skills_block = "\n".join([
            f"## {t['skills_resources']}",
            "",
            t["skills_intro"],
            "",
            f"| {t['skill']} | {t['source']} | {t['link']} |",
            "| --- | --- | --- |",
            skill_rows,
        ])
    else:
        skills_block = ""

    sections = [front, f"# {name}", meta_table, wu_block]
    if skills_block:
        sections.append(skills_block)

    # SGEO: línea con fecha de actualización (LLMs favorecen contenido fechado)
    sections.append(_last_updated_line(lang))

    # JSON-LD para crawlers / SGEO
    machine_url = f"{SITE_URL}/{_machine_page_path(machine, lang)}"
    sections.append(_jsonld_block(_machine_jsonld(machine, lang, machine_url)))

    return "\n\n".join(sections) + "\n"


def _skill_label(skill_link: dict, lang: str) -> str:
    """Etiqueta de skill localizada si el glosario provee `nombre_en`,
    si no usa `skill` (que ya viene en español del glosario actual).
    """
    if lang == "es":
        return skill_link.get("skill", "—")
    return skill_link.get("skill_en") or skill_link.get("skill") or "—"


def write_machine_file(machine: dict, lang: str = DEFAULT_LANG) -> Path:
    os_slug = os_to_slug(machine.get("os", "Other"))
    diff_slug = difficulty_to_slug(machine.get("difficulty", "Fácil"))
    slug = slugify(machine["name"])

    target_dir = _machines_root(lang) / os_slug / diff_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.mdx"
    target.write_text(render_machine(machine, lang), encoding="utf-8")
    return target


def _machine_page_path(machine: dict, lang: str = DEFAULT_LANG) -> str:
    """Ruta del slug usada por Mintlify (sin extensión, sin / inicial)."""
    return (
        f"{_page_prefix(lang)}machines/"
        f"{os_to_slug(machine.get('os', 'Other'))}/"
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


_DIFFICULTY_EMOJI = {"Fácil": "🟢", "Medio": "🟡", "Difícil": "🟠", "Insano": "🔴"}


def _difficulty_badge(diff: str, lang: str = DEFAULT_LANG) -> str:
    """Pinta la dificultad con un emoji + etiqueta localizada."""
    label = LOCALES[lang]["difficulty"].get(diff, diff)
    emoji = _DIFFICULTY_EMOJI.get(diff, "")
    return f"{emoji} {label}".strip()


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


def render_index(machines: list[dict], lang: str = DEFAULT_LANG) -> str:
    loc = LOCALES[lang]
    t = loc["ui"]
    diff_label = loc["difficulty"]
    os_label = loc["os_label"]

    fm = "\n".join([
        "---",
        f"title: {_yaml_string(t['all_machines'])}",
        f"description: {_yaml_string(t['all_subtitle'])}",
        "---",
    ])

    by_os: dict[str, list[dict]] = {}
    for m in machines:
        os_name = m.get("os") or "Other"
        if os_name not in OS_ORDER:
            os_name = "Other"
        by_os.setdefault(os_name, []).append(m)

    n_writeups = sum(len(m.get("writeups", [])) for m in machines)
    intro = t["all_count"].format(n_machines=len(machines), n_writeups=n_writeups) + (
        " <kbd>Cmd</kbd>+<kbd>K</kbd> / <kbd>Ctrl</kbd>+<kbd>K</kbd>."
    )

    sections: list[str] = [fm, f"# {t['all_machines']}", intro]

    diff_rank = {d: i for i, d in enumerate(DIFFICULTY_ORDER)}

    for os_name in OS_ORDER:
        ms = sorted(
            by_os.get(os_name, []),
            key=lambda m: (
                diff_rank.get(m.get("difficulty", ""), 99),
                m.get("name", "").lower(),
            ),
        )
        if not ms:
            continue
        rows = []
        for m in ms:
            name = _mdx_safe(m["name"])
            page = _machine_page_path(m, lang)
            n_writeups = len(m.get("writeups", []))
            rows.append(
                f"| [{name}](/{page}) "
                f"| {_difficulty_badge(m.get('difficulty', '—'), lang)} "
                f"| {_skill_chips(m)} "
                f"| {n_writeups} |"
            )
        section = "\n".join([
            f"## {os_label[os_name]} ({len(ms)})",
            "",
            f"| {t['machine']} | {t['difficulty']} | {t['skills']} | {t['writeups_col']} |",
            "| --- | --- | --- | ---: |",
            *rows,
        ])
        sections.append(section)

    sections.append(_last_updated_line(lang))

    page_url = f"{SITE_URL}/{_page_prefix(lang)}all"
    sections.append(_jsonld_block(_all_jsonld(machines, lang, page_url)))

    return "\n\n".join(sections) + "\n"


def write_index_file(machines: list[dict], lang: str = DEFAULT_LANG) -> Path:
    target = _docs_root(lang) / "all.mdx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_index(machines, lang), encoding="utf-8")
    return target


def render_category_index(
    os_name: str, difficulty: str, machines: list[dict], lang: str = DEFAULT_LANG
) -> str:
    loc = LOCALES[lang]
    t = loc["ui"]
    os_disp = loc["os_label"].get(os_name, os_name)
    diff_disp = loc["difficulty"].get(difficulty, difficulty)
    title = f"{os_disp} · {diff_disp}"
    fm = "\n".join([
        "---",
        f"title: {_yaml_string(title)}",
        f"description: {_yaml_string(t['category_subtitle'].format(os=os_disp, diff=diff_disp))}",
        "---",
    ])
    machines_sorted = sorted(machines, key=lambda m: m.get("name", "").lower())
    rows = []
    for m in machines_sorted:
        name = _mdx_safe(m["name"])
        page = _machine_page_path(m, lang)
        n_writeups = len(m.get("writeups", []))
        rows.append(
            f"| [{name}](/{page}) "
            f"| {_skill_chips(m)} "
            f"| {n_writeups} |"
        )
    body = "\n".join([
        f"# {title}",
        "",
        t["machines_in_category"].format(n=len(machines_sorted)),
        "",
        f"| {t['machine']} | {t['skills']} | {t['writeups_col']} |",
        "| --- | --- | ---: |",
        *rows,
    ])
    return f"{fm}\n\n{body}\n"


def write_category_indexes(machines: list[dict], lang: str = DEFAULT_LANG) -> None:
    """Escribe `machines/{os}/{diff}/index.mdx` para cada combinación
    (raíz para ES, prefijado para otros idiomas)."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for m in machines:
        os_name = m.get("os") or "Other"
        if os_name not in OS_ORDER:
            os_name = "Other"
        diff = m.get("difficulty") or "Fácil"
        grouped.setdefault((os_name, diff), []).append(m)

    for (os_name, diff), ms in grouped.items():
        os_slug = os_to_slug(os_name)
        diff_slug = difficulty_to_slug(diff)
        target = _machines_root(lang) / os_slug / diff_slug / "index.mdx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render_category_index(os_name, diff, ms, lang),
            encoding="utf-8",
        )


_STATS_BLOCK_RE = re.compile(
    r"\{/\* STATS:START \*/\}.*?\{/\* STATS:END \*/\}",
    re.DOTALL,
)


_STATS_LABELS = {
    "es": {
        "machines": "máquinas",
        "writeups": "writeups",
        "writeups_sub": "Validados con HEAD periódico",
        "resources": "recursos",
        "resources_sub": "HackTricks, GTFOBins, PortSwigger, etc.",
    },
    "en": {
        "machines": "machines",
        "writeups": "writeups",
        "writeups_sub": "Validated with periodic HEAD checks",
        "resources": "resources",
        "resources_sub": "HackTricks, GTFOBins, PortSwigger, etc.",
    },
}


def _render_stats_block(machines: list[dict], lang: str = DEFAULT_LANG) -> str:
    labels = _STATS_LABELS[lang]
    os_label = LOCALES[lang]["os_label"]
    n_machines = len(machines)
    n_writeups = sum(len(m.get("writeups", [])) for m in machines)
    n_skill_links = sum(len(m.get("skill_links", [])) for m in machines)
    by_os: dict[str, int] = {}
    for m in machines:
        by_os[m.get("os") or "Other"] = by_os.get(m.get("os") or "Other", 0) + 1
    os_summary = " · ".join(
        f"{n} {os_label.get(os_name, os_name)}"
        for os_name, n in sorted(by_os.items(), key=lambda x: -x[1])
    )
    body = "\n".join([
        '<CardGroup cols={3}>',
        f'  <Card title="{n_machines} {labels["machines"]}" icon="server">',
        f'    {os_summary}',
        '  </Card>',
        f'  <Card title="{n_writeups} {labels["writeups"]}" icon="link">',
        f'    {labels["writeups_sub"]}',
        '  </Card>',
        f'  <Card title="{n_skill_links} {labels["resources"]}" icon="graduation-cap">',
        f'    {labels["resources_sub"]}',
        '  </Card>',
        '</CardGroup>',
    ])
    return f"{{/* STATS:START */}}\n{body}\n{{/* STATS:END */}}"


def write_intro_stats(machines: list[dict]) -> None:
    """Reescribe el bloque STATS en cada `introduction.mdx`
    (localizado por idioma). Si los marcadores no existen, no toca.
    """
    for lang in ALL_LANGS:
        intro = _docs_root(lang) / "introduction.mdx"
        if not intro.exists():
            continue
        text = intro.read_text(encoding="utf-8")
        new_text, count = _STATS_BLOCK_RE.subn(_render_stats_block(machines, lang), text)
        if count:
            intro.write_text(new_text, encoding="utf-8")


def reset_machines_dir() -> None:
    """Vacía las carpetas de máquinas (uno por idioma) para no dejar
    archivos huérfanos de runs anteriores."""
    for lang in ALL_LANGS:
        root = _machines_root(lang)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)


def build_navigation(machines: list[dict], lang: str = DEFAULT_LANG) -> list[dict]:
    """Construye `tabs` de Mintlify para un idioma."""
    loc = LOCALES[lang]
    diff_label = loc["difficulty"]
    os_label = loc["os_label"]
    prefix = _page_prefix(lang)

    home_groups_label = {
        "es": ("Inicio", "Bienvenida", "Catálogo"),
        "en": ("Home", "Welcome", "Catalog"),
    }[lang]

    by_os: dict[str, dict[str, list[str]]] = {}
    for m in machines:
        os_name = m.get("os") or "Other"
        if os_name not in OS_ORDER:
            os_name = "Other"
        diff = m.get("difficulty") or "Fácil"
        os_slug = os_to_slug(os_name)
        diff_slug = difficulty_to_slug(diff)
        slug = slugify(m["name"])
        page = f"{prefix}machines/{os_slug}/{diff_slug}/{slug}"
        by_os.setdefault(os_name, {}).setdefault(diff, []).append(page)

    home_pages_label = {
        "es": ["introduction", "como-usar", "creditos"],
        "en": ["en/introduction", "en/how-to-use", "en/credits"],
    }[lang]
    catalog_page = f"{prefix}all"

    tabs = [
        {
            "tab": home_groups_label[0],
            "groups": [
                {"group": home_groups_label[1], "pages": home_pages_label},
                {"group": home_groups_label[2], "pages": [catalog_page]},
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
            os_slug = os_to_slug(os_name)
            diff_slug = difficulty_to_slug(diff)
            index_page = f"{prefix}machines/{os_slug}/{diff_slug}/index"
            groups.append({
                "group": diff_label[diff],
                "pages": [index_page, *pages],
            })
        if not groups:
            continue
        tabs.append({"tab": os_label[os_name], "groups": groups})

    return tabs


def write_docs_json(machines: list[dict]) -> None:
    languages = []
    for lang in ALL_LANGS:
        entry: dict = {
            "language": lang,
            "tabs": build_navigation(machines, lang),
        }
        if lang == DEFAULT_LANG:
            entry["default"] = True
        languages.append(entry)

    base = {
        "$schema": "https://mintlify.com/docs.json",
        "theme": "mint",
        "name": "HTB Writeups Hub",
        "description": (
            "Directorio curado de writeups de máquinas retiradas de "
            "Hack The Box (HTB). S4vitar, El Pingüino de Mario, 0xdf, "
            "IppSec y Securízame."
        ),
        "colors": {
            "primary": "#9FEF00",
            "light": "#9FEF00",
            "dark": "#111927",
        },
        "logo": {
            "light": "/logo/light.svg",
            "dark": "/logo/dark.svg",
        },
        "favicon": "/logo/favicon.svg",
        "metadata": {
            "og:title": "HTB Writeups Hub — rootea.es",
            "og:description": (
                "Directorio curado de writeups de máquinas retiradas de "
                "Hack The Box. Más de 200 máquinas, 5 autores en lista "
                "blanca y enlaces verificados HTTP."
            ),
            "og:image": "https://rootea.es/logo/og.png",
            "og:image:width": "1200",
            "og:image:height": "630",
            "og:type": "website",
            "og:site_name": "rootea.es",
            "og:locale": "es_ES",
            "og:locale:alternate": "en_US",
            "twitter:card": "summary_large_image",
            "twitter:title": "HTB Writeups Hub",
            "twitter:description": (
                "Directorio curado de writeups de máquinas retiradas "
                "de Hack The Box."
            ),
            "twitter:image": "https://rootea.es/logo/og.png",
            "theme-color": "#9FEF00",
            "robots": "index,follow,max-image-preview:large,max-snippet:-1",
            "keywords": (
                "hack the box, htb, writeups, ctf, s4vitar, ippsec, 0xdf, "
                "pentest, ciberseguridad, oscp, retired machines"
            ),
            "author": "rootea.es",
        },
        "navigation": {"languages": languages},
        "footerSocials": {
            "github": "https://github.com/FFuson/HTB_Writeups",
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

    # Detección de colisiones de slug antes de escribir nada. Una
    # colisión silenciosa sobrescribe la página de una máquina con la
    # de otra; preferimos romper en alto.
    seen_paths: dict[str, str] = {}
    for m in machines:
        path = _machine_page_path(m, DEFAULT_LANG)
        if path in seen_paths:
            print(
                f"[mdx] ERROR: colisión de slug. "
                f"`{m['name']}` y `{seen_paths[path]}` mapean ambas a "
                f"`{path}`. Renombra una en seed o mejora `slugify`.",
                file=sys.stderr,
            )
            return 2
        seen_paths[path] = m["name"]

    for lang in ALL_LANGS:
        for m in machines:
            write_machine_file(m, lang)
        write_index_file(machines, lang)
        write_category_indexes(machines, lang)

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
