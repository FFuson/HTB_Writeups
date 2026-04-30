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
import os
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

from scripts.config import (
    AUTHORS,
    DATA_DIR,
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


def _website_jsonld(lang: str) -> dict:
    """JSON-LD WebSite con SearchAction (rich result: caja de búsqueda
    en Google que apunta directamente al buscador del sitio).
    """
    base = SITE_URL + ("" if lang == DEFAULT_LANG else f"/{lang}")
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "rootea.es · HTB Writeups Hub",
        "alternateName": "rootea.es",
        "url": SITE_URL,
        "inLanguage": lang,
        "description": (
            "Directorio curado de writeups de máquinas retiradas de "
            "Hack The Box"
            if lang == "es"
            else "Curated directory of writeups for retired Hack The "
                 "Box machines"
        ),
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base}/all?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def _faqpage_jsonld(faqs: list[tuple[str, str]], lang: str) -> dict:
    """JSON-LD FAQPage; los buscadores generativos lo usan para
    devolver la respuesta literal en SERP.
    """
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "inLanguage": lang,
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in faqs
        ],
    }


def _course_jsonld(lang: str) -> dict:
    """JSON-LD Course para /roadmap-oscp; rich snippet con badge."""
    base = SITE_URL + ("" if lang == DEFAULT_LANG else f"/{lang}")
    return {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": "Roadmap OSCP" if lang == "es" else "OSCP Roadmap",
        "description": (
            "Selección curada de 30 máquinas de Hack The Box ordenadas "
            "para preparar el examen OSCP."
            if lang == "es"
            else "Curated selection of 30 Hack The Box machines ordered "
                 "to prepare for the OSCP exam."
        ),
        "url": f"{base}/roadmap-oscp",
        "inLanguage": lang,
        "provider": {
            "@type": "Organization",
            "name": "rootea.es",
            "url": SITE_URL,
        },
        "educationalLevel": "Intermediate",
        "about": [
            {"@type": "Thing", "name": "Hack The Box"},
            {"@type": "Thing", "name": "OSCP"},
            {"@type": "Thing", "name": "Penetration testing"},
        ],
        "hasCourseInstance": {
            "@type": "CourseInstance",
            "courseMode": "online",
            "courseWorkload": "PT60H",
        },
    }


def _persons_jsonld(lang: str) -> dict:
    """JSON-LD ItemList con los autores de la lista blanca como
    Person/Organization (legitima la página /creditos para Google).
    """
    items = []
    for idx, (name, meta) in enumerate(AUTHORS.items(), start=1):
        items.append(
            {
                "@type": "ListItem",
                "position": idx,
                "item": {
                    "@type": "Person",
                    "name": name,
                    "url": meta.get("homepage", "#"),
                    "knowsAbout": "Penetration testing, Hack The Box",
                    "inLanguage": meta.get("idioma", "EN").lower(),
                },
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Authors whitelisted on rootea.es",
        "inLanguage": lang,
        "itemListElement": items,
    }


# FAQs extraídas de introduction.mdx — duplicadas aquí en formato puro
# para JSON-LD, mantienen sincronía con el contenido visible.
_FAQ_ES: list[tuple[str, str]] = [
    (
        "¿Qué es Hack The Box (HTB)?",
        "Hack The Box (HTB) es una plataforma online de entrenamiento "
        "en ciberseguridad ofensiva, fundada en 2017. Ofrece máquinas "
        "vulnerables que el usuario debe comprometer para obtener "
        "flags, puntuando en un ranking público.",
    ),
    (
        "¿Qué es una máquina retirada?",
        "Una máquina HTB se considera retirada cuando deja de otorgar "
        "puntos. A partir de ese momento, los términos del servicio "
        "permiten publicar writeups públicamente. Este hub sólo indexa "
        "máquinas retiradas.",
    ),
    (
        "¿De dónde sale el catálogo?",
        "El catálogo se construye de tres fuentes: el dataset "
        "comunitario de htbmachines.github.io, un seed local con "
        "máquinas clásicas y, opcionalmente, la API oficial de HTB.",
    ),
    (
        "¿Quién mantiene los writeups enlazados?",
        "Los writeups son obra de sus respectivos autores: S4vitar, "
        "El Pingüino de Mario, Securízame, 0xdf y IppSec. Este hub "
        "sólo indexa los enlaces; no aloja ni modifica el contenido.",
    ),
    (
        "¿Cómo se valida que un enlace funciona?",
        "Cada URL pasa por una petición HEAD antes de publicarse. Los "
        "enlaces que devuelven 4xx o 5xx se descartan. La validación "
        "se ejecuta semanalmente vía GitHub Action.",
    ),
]

_FAQ_EN: list[tuple[str, str]] = [
    (
        "What is Hack The Box (HTB)?",
        "Hack The Box (HTB) is an online offensive cybersecurity "
        "training platform founded in 2017. It provides vulnerable "
        "machines that users must compromise to obtain flags, scoring "
        "in a public ranking.",
    ),
    (
        "What is a retired machine?",
        "An HTB machine is considered retired once it stops granting "
        "ranking points. From that moment on, the terms of service "
        "allow publishing writeups openly. This hub only indexes "
        "retired machines.",
    ),
    (
        "Where does the catalog come from?",
        "The catalog is built from three sources: the community-"
        "maintained dataset at htbmachines.github.io, a local seed of "
        "classic machines, and optionally the official HTB API.",
    ),
    (
        "Who maintains the linked writeups?",
        "The writeups are produced by their respective authors: "
        "S4vitar, El Pingüino de Mario, Securízame, 0xdf, and IppSec. "
        "This hub only indexes the links; it does not host or modify "
        "the original content.",
    ),
    (
        "How is link validity verified?",
        "Every URL gets a HEAD request before being published. Links "
        "returning 4xx or 5xx are discarded. Validation runs weekly "
        "via a GitHub Action.",
    ),
]


def _breadcrumb_jsonld(machine: dict, lang: str) -> dict:
    """JSON-LD BreadcrumbList: Home > OS > Difficulty > Machine."""
    loc = LOCALES[lang]
    os_name = machine.get("os") or "Other"
    diff = machine.get("difficulty") or "Fácil"
    home_url = SITE_URL + ("" if lang == DEFAULT_LANG else f"/{lang}")
    os_url = (
        f"{SITE_URL}/{_page_prefix(lang)}machines/{os_to_slug(os_name)}/"
        f"{difficulty_to_slug(diff)}/index"
    )
    machine_url = f"{SITE_URL}/{_machine_page_path(machine, lang)}"
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home" if lang == "en" else "Inicio",
                "item": home_url,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": loc["os_label"].get(os_name, os_name),
                "item": os_url,
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": loc["difficulty"].get(diff, diff),
                "item": os_url,
            },
            {
                "@type": "ListItem",
                "position": 4,
                "name": machine["name"],
                "item": machine_url,
            },
        ],
    }


def _related_machines(
    machine: dict, all_machines: list[dict], k: int = 5
) -> list[dict]:
    """Devuelve las `k` máquinas más parecidas por skills compartidas
    (Jaccard simple sobre los `skill_links` detectados, fallback a
    coincidencia de SO+dificultad).
    """
    own_skills = {
        s.get("skill")
        for s in machine.get("skill_links", [])
        if s.get("skill")
    }
    if not own_skills:
        return []

    scored: list[tuple[float, dict]] = []
    for other in all_machines:
        if other["name"] == machine["name"]:
            continue
        other_skills = {
            s.get("skill")
            for s in other.get("skill_links", [])
            if s.get("skill")
        }
        if not other_skills:
            continue
        intersection = len(own_skills & other_skills)
        if intersection == 0:
            continue
        union = len(own_skills | other_skills)
        jaccard = intersection / union
        # Empate desempata por mismo SO/dificultad
        bonus = 0.0
        if other.get("os") == machine.get("os"):
            bonus += 0.05
        if other.get("difficulty") == machine.get("difficulty"):
            bonus += 0.03
        scored.append((jaccard + bonus, other))

    scored.sort(key=lambda kv: -kv[0])
    return [m for _, m in scored[:k]]


def _format_writeup_row_i18n(w: dict, t: dict) -> str:
    autor = w.get("autor", "Anónimo")
    idioma = w.get("idioma", "—")
    formato = w.get("formato", "—")
    url = w.get("url", "#")
    bandera = "🇪🇸" if idioma == "ES" else "🇬🇧" if idioma == "EN" else "🌐"
    return f"| {bandera} {idioma} | **{autor}** | {formato} | [{t['open']}]({url}) |"


def render_machine(
    machine: dict,
    lang: str = DEFAULT_LANG,
    all_machines: list[dict] | None = None,
) -> str:
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

    og_image = f"{SITE_URL}/og/{slugify(name)}.svg"
    fm_lines = [
        "---",
        f"title: {_yaml_string(name)}",
        f"description: {_yaml_string(t['machine_page_desc'].format(name=name))}",
        f'"og:image": {_yaml_string(og_image)}',
        f'"twitter:image": {_yaml_string(og_image)}',
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

    # Skills relacionadas (del grafo del glosario)
    related_skills = machine.get("related_skills") or []
    if related_skills:
        related_label = (
            "Skills relacionadas que conviene dominar"
            if lang == "es"
            else "Related skills worth mastering"
        )
        chips = " · ".join(
            _mdx_safe(s.get("skill" if lang == "es" else "skill_en", "—"))
            for s in related_skills[:8]
        )
        sections.append(f"## {related_label}\n\n{chips}")

    # Recomendaciones cruzadas por skills compartidas
    if all_machines:
        related = _related_machines(machine, all_machines, k=5)
        if related:
            related_label = (
                "Si te gustó esta máquina, prueba"
                if lang == "es" else "If you liked this machine, try"
            )
            related_rows = "\n".join(
                f"- [{r['name']}](/{_machine_page_path(r, lang)}) — "
                f"{LOCALES[lang]['os_label'].get(r.get('os', 'Other'), r.get('os'))}, "
                f"{LOCALES[lang]['difficulty'].get(r.get('difficulty', ''), r.get('difficulty', ''))}"
                for r in related
            )
            related_block = f"## {related_label}\n\n{related_rows}"
            sections.append(related_block)

    # CTA hacia GitHub Discussions (búsqueda inteligente del thread
    # asociado por título de la máquina). Genera contenido fresco y
    # backlinks al repo, ambos buenos para SEO.
    discuss_label = (
        "💬 Discutir esta máquina"
        if lang == "es"
        else "💬 Discuss this machine"
    )
    discuss_q = urllib.parse.quote(machine["name"])
    discuss_url = (
        f"https://github.com/FFuson/HTB_Writeups/discussions"
        f"?discussions_q={discuss_q}"
    )
    sections.append(
        f"---\n\n[{discuss_label}]({discuss_url}) · "
        + ("¿Hay un truco que te ayudó? Compártelo en GitHub Discussions."
           if lang == "es"
           else "Got a tip that helped you? Share it on GitHub Discussions.")
    )

    # SGEO: línea con fecha de actualización (LLMs favorecen contenido fechado)
    sections.append(_last_updated_line(lang))

    # JSON-LD para crawlers / SGEO
    machine_url = f"{SITE_URL}/{_machine_page_path(machine, lang)}"
    sections.append(_jsonld_block(_machine_jsonld(machine, lang, machine_url)))
    sections.append(_jsonld_block(_breadcrumb_jsonld(machine, lang)))

    return "\n\n".join(sections) + "\n"


def _skill_label(skill_link: dict, lang: str) -> str:
    """Etiqueta de skill localizada si el glosario provee `nombre_en`,
    si no usa `skill` (que ya viene en español del glosario actual).
    """
    if lang == "es":
        return skill_link.get("skill", "—")
    return skill_link.get("skill_en") or skill_link.get("skill") or "—"


def write_machine_file(
    machine: dict,
    lang: str = DEFAULT_LANG,
    all_machines: list[dict] | None = None,
) -> Path:
    os_slug = os_to_slug(machine.get("os", "Other"))
    diff_slug = difficulty_to_slug(machine.get("difficulty", "Fácil"))
    slug = slugify(machine["name"])

    target_dir = _machines_root(lang) / os_slug / diff_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{slug}.mdx"
    target.write_text(
        render_machine(machine, lang, all_machines=all_machines),
        encoding="utf-8",
    )
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


_DIFFICULTY_CLASS = {
    "Fácil": "easy",
    "Medio": "medium",
    "Difícil": "hard",
    "Insano": "insane",
}

_DIFFICULTY_LABEL_EN = {
    "Fácil": "EASY",
    "Medio": "MEDIUM",
    "Difícil": "HARD",
    "Insano": "INSANE",
}


def _difficulty_badge(diff: str, lang: str = DEFAULT_LANG) -> str:
    """Chip HTML estilo HTB: monoespacial, color por nivel."""
    label = _DIFFICULTY_LABEL_EN.get(diff, diff).upper()
    cls = _DIFFICULTY_CLASS.get(diff, "easy")
    return f'<span class="dbadge dbadge-{cls}">{label}</span>'


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

    # Dashboard: 3 charts client-side rellenados por custom.js
    charts_label_os = "Distribución por SO" if lang == "es" else "By OS"
    charts_label_diff = "Por dificultad" if lang == "es" else "By difficulty"
    charts_label_year = "Retiradas por año" if lang == "es" else "Retired per year"
    charts_block = (
        '<div id="rootea-charts">\n'
        f'  <div className="rootea-chart"><h3>{charts_label_os}</h3>'
        '<canvas id="chart-os" height="180"></canvas></div>\n'
        f'  <div className="rootea-chart"><h3>{charts_label_diff}</h3>'
        '<canvas id="chart-difficulty" height="180"></canvas></div>\n'
        f'  <div className="rootea-chart"><h3>{charts_label_year}</h3>'
        '<canvas id="chart-year" height="180"></canvas></div>\n'
        '</div>'
    )

    # Filtros chips (multi-selección, JS toggle)
    f_os = "OS" if lang == "es" else "OS"
    f_diff = "Dificultad" if lang == "es" else "Difficulty"
    diff_keys = [
        ("Fácil", "EASY" if lang == "en" else "FÁCIL"),
        ("Medio", "MEDIUM" if lang == "en" else "MEDIO"),
        ("Difícil", "HARD" if lang == "en" else "DIFÍCIL"),
        ("Insano", "INSANE" if lang == "en" else "INSANO"),
    ]
    chips: list[str] = [f'<span className="rootea-filter-group-label">{f_os}</span>']
    for os_canon in OS_ORDER:
        if os_canon not in by_os:
            continue
        label_os = loc["os_label"].get(os_canon, os_canon)
        chips.append(
            f'<span className="rootea-chip" data-filter-type="os" '
            f'data-filter-value="{label_os}">{label_os}</span>'
        )
    chips.append(
        f'<span className="rootea-filter-group-label" '
        'style={{ marginLeft: "1rem" }}>' + f_diff + '</span>'
    )
    for canon, lbl in diff_keys:
        chips.append(
            f'<span className="rootea-chip" data-filter-type="diff" '
            f'data-filter-value="{lbl}">{lbl}</span>'
        )
    filters_block = '<div id="rootea-filters">\n' + "\n".join(chips) + "\n</div>"

    sections: list[str] = [
        fm,
        f"# {t['all_machines']}",
        intro,
        charts_block,
        filters_block,
    ]

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

    # Tabla ordenable client-side al hacer click en cabeceras
    sections.append(_SORT_SCRIPT.strip())

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


# ----------------------------------------------------------------------------
# Páginas extra: Random, Recientes, Cobertura por autor
# ----------------------------------------------------------------------------

# Script JS embebido para que la tabla maestra (/all) sea ordenable
# client-side al hacer click en las cabeceras. Vanilla JS, sin
# dependencias.
_SORT_SCRIPT = """
<script>
(function () {
  function comparer(idx, asc) {
    return function (a, b) {
      const v1 = a.children[idx].innerText.trim();
      const v2 = b.children[idx].innerText.trim();
      const n1 = parseFloat(v1.replace(/[^0-9.-]/g, ''));
      const n2 = parseFloat(v2.replace(/[^0-9.-]/g, ''));
      if (!isNaN(n1) && !isNaN(n2)) return asc ? n1 - n2 : n2 - n1;
      return asc
        ? v1.localeCompare(v2, undefined, { numeric: true })
        : v2.localeCompare(v1, undefined, { numeric: true });
    };
  }
  function init() {
    document.querySelectorAll('table').forEach(function (table) {
      table.querySelectorAll('th').forEach(function (th, idx) {
        th.style.cursor = 'pointer';
        th.title = 'Click para ordenar';
        let asc = true;
        th.addEventListener('click', function () {
          const tbody = table.tBodies[0];
          if (!tbody) return;
          Array.from(tbody.rows)
            .sort(comparer(idx, asc))
            .forEach(function (row) { tbody.appendChild(row); });
          asc = !asc;
        });
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
</script>
"""


def render_recent(machines: list[dict], lang: str, top_n: int = 20) -> str:
    """Tabla con las últimas N máquinas retiradas, por release_date desc."""
    loc = LOCALES[lang]
    t = loc["ui"]
    title = "Recién retiradas" if lang == "es" else "Recently retired"
    intro_es = (
        f"Las {top_n} máquinas más recientes según fecha de retirada. "
        "Se actualiza con cada regeneración del catálogo."
    )
    intro_en = (
        f"The {top_n} most recent machines by retirement date. "
        "Updated on every catalog regeneration."
    )
    fm = "\n".join([
        "---",
        f"title: {_yaml_string(title)}",
        f"description: {_yaml_string(intro_en if lang == 'en' else intro_es)}",
        "---",
    ])
    with_dates = [
        m for m in machines if (m.get("release_date") or "").strip()
    ]
    with_dates.sort(key=lambda m: m["release_date"], reverse=True)
    top = with_dates[:top_n]
    rows = []
    for m in top:
        page = _machine_page_path(m, lang)
        rows.append(
            f"| {m.get('release_date', '—')} "
            f"| [{_mdx_safe(m['name'])}](/{page}) "
            f"| {LOCALES[lang]['os_label'].get(m.get('os', 'Other'), m.get('os'))} "
            f"| {_difficulty_badge(m.get('difficulty', '—'), lang)} "
            f"| {_skill_chips(m)} |"
        )
    date_h = "Fecha" if lang == "es" else "Date"
    body = "\n".join([
        f"# {title}",
        "",
        intro_en if lang == "en" else intro_es,
        "",
        f"| {date_h} | {t['machine']} | {t['system']} | {t['difficulty']} | {t['skills']} |",
        "| --- | --- | --- | --- | --- |",
        *rows,
    ])
    return f"{fm}\n\n{body}\n\n{_last_updated_line(lang)}\n"


def write_recent_file(machines: list[dict], lang: str = DEFAULT_LANG) -> Path:
    target = _docs_root(lang) / "recientes.mdx"
    target.write_text(render_recent(machines, lang), encoding="utf-8")
    return target


def render_author_coverage(machines: list[dict], lang: str) -> str:
    """Tabla con cuántas máquinas cubre cada autor de la lista blanca."""
    title = "Cobertura por autor" if lang == "es" else "Author coverage"
    desc_es = (
        "Cuántas máquinas del catálogo tienen al menos un writeup "
        "validado por cada autor."
    )
    desc_en = (
        "How many machines in the catalog have at least one validated "
        "writeup from each author."
    )
    fm = "\n".join([
        "---",
        f"title: {_yaml_string(title)}",
        f"description: {_yaml_string(desc_en if lang == 'en' else desc_es)}",
        "---",
    ])
    coverage: dict[str, int] = {a: 0 for a in AUTHORS}
    for m in machines:
        seen_in_machine: set[str] = set()
        for w in m.get("writeups", []):
            autor = w.get("autor")
            if autor in AUTHORS and autor not in seen_in_machine:
                coverage[autor] += 1
                seen_in_machine.add(autor)
    total = len(machines)
    rows = []
    for autor, n in sorted(coverage.items(), key=lambda kv: -kv[1]):
        pct = (n / total * 100) if total else 0
        meta = AUTHORS.get(autor, {})
        homepage = meta.get("homepage", "#")
        idioma = meta.get("idioma", "—")
        bandera = "🇪🇸" if idioma == "ES" else "🇬🇧"
        rows.append(
            f"| [{autor}]({homepage}) "
            f"| {bandera} {idioma} "
            f"| {n} / {total} "
            f"| {pct:.1f}% |"
        )
    aut_h = "Autor" if lang == "es" else "Author"
    lang_h = "Idioma" if lang == "es" else "Language"
    cov_h = "Cobertura" if lang == "es" else "Coverage"
    pct_h = "%"
    body = "\n".join([
        f"# {title}",
        "",
        desc_en if lang == "en" else desc_es,
        "",
        f"| {aut_h} | {lang_h} | {cov_h} | {pct_h} |",
        "| --- | --- | ---: | ---: |",
        *rows,
    ])
    return f"{fm}\n\n{body}\n\n{_last_updated_line(lang)}\n"


def write_author_coverage(machines: list[dict], lang: str = DEFAULT_LANG) -> Path:
    target = _docs_root(lang) / "cobertura-autores.mdx"
    target.write_text(render_author_coverage(machines, lang), encoding="utf-8")
    return target


def render_changelog(history: list[dict], lang: str) -> str:
    """Página /cambios con timeline de los runs semanales."""
    title = "Histórico de cambios" if lang == "es" else "Change history"
    desc = (
        "Cambios detectados en cada regeneración semanal del catálogo."
        if lang == "es"
        else "Changes detected on each weekly catalog regeneration."
    )
    fm = "\n".join([
        "---",
        f"title: {_yaml_string(title)}",
        f"description: {_yaml_string(desc)}",
        "---",
    ])

    if not history:
        body = (
            f"# {title}\n\n{desc}\n\n"
            + ("_Aún sin entradas registradas._"
               if lang == "es"
               else "_No entries logged yet._")
        )
        return f"{fm}\n\n{body}\n"

    sections = [f"# {title}", desc, ""]
    for entry in history:
        date = entry.get("date", "—")
        added = entry.get("added", [])
        removed = entry.get("removed", [])
        changed = entry.get("changed", [])
        sections.append(f"## {date}")
        if entry.get("first_run"):
            sections.append(
                f"_Primera ingesta del catálogo: {len(added)} máquinas._"
                if lang == "es"
                else f"_First catalog ingest: {len(added)} machines._"
            )
            continue
        if added:
            label = "Nuevas" if lang == "es" else "New"
            sections.append(f"**{label}**: " + ", ".join(_mdx_safe(n) for n in added))
        if removed:
            label = "Retiradas" if lang == "es" else "Removed"
            sections.append(f"**{label}**: " + ", ".join(_mdx_safe(n) for n in removed))
        if changed:
            label = "Cambios" if lang == "es" else "Changes"
            chunks = []
            for c in changed[:30]:
                w = c["writeups_delta"]
                r = c["resources_delta"]
                pieces = []
                if w:
                    pieces.append(f"{w:+d} writeups")
                if r:
                    pieces.append(f"{r:+d} recursos")
                chunks.append(f"{_mdx_safe(c['name'])} ({', '.join(pieces)})")
            extra = ""
            if len(changed) > 30:
                extra = f" _(+{len(changed) - 30} más)_"
            sections.append(f"**{label}**: " + ", ".join(chunks) + extra)

    return f"{fm}\n\n" + "\n\n".join(sections) + f"\n\n{_last_updated_line(lang)}\n"


def write_changelog_file(lang: str = DEFAULT_LANG) -> Path:
    history_file = DATA_DIR / "changelog.json"
    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    target = _docs_root(lang) / "cambios.mdx"
    target.write_text(render_changelog(history, lang), encoding="utf-8")
    return target


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
        "machines_label": "máquinas indexadas",
        "writeups_label": "writeups validados",
        "resources_label": "recursos por skill",
    },
    "en": {
        "machines_label": "indexed machines",
        "writeups_label": "validated writeups",
        "resources_label": "skill resources",
    },
}


def _render_stats_block(machines: list[dict], lang: str = DEFAULT_LANG) -> str:
    labels = _STATS_LABELS[lang]
    n_machines = len(machines)
    n_writeups = sum(len(m.get("writeups", [])) for m in machines)
    n_skill_links = sum(len(m.get("skill_links", [])) for m in machines)
    body = "\n".join([
        '  <div className="rootea-hero-counters">',
        '    <div className="rootea-counter">',
        f'      <div className="rootea-counter-num">{n_machines}</div>',
        f'      <div className="rootea-counter-label">{labels["machines_label"]}</div>',
        '    </div>',
        '    <div className="rootea-counter">',
        f'      <div className="rootea-counter-num">{n_writeups}</div>',
        f'      <div className="rootea-counter-label">{labels["writeups_label"]}</div>',
        '    </div>',
        '    <div className="rootea-counter">',
        f'      <div className="rootea-counter-num">{n_skill_links}</div>',
        f'      <div className="rootea-counter-label">{labels["resources_label"]}</div>',
        '    </div>',
        '  </div>',
    ])
    return f"  {{/* STATS:START */}}\n{body}\n  {{/* STATS:END */}}"


_JSONLD_BLOCK_RE = re.compile(
    r"\{/\* JSONLD:START \*/\}.*?\{/\* JSONLD:END \*/\}",
    re.DOTALL,
)


def _wrap_jsonld_marker(payloads: list[dict]) -> str:
    """Devuelve el bloque entre marcadores con N JSON-LD scripts."""
    parts = ["{/* JSONLD:START */}"]
    for payload in payloads:
        parts.append(_jsonld_block(payload))
    parts.append("{/* JSONLD:END */}")
    return "\n".join(parts)


def _inject_jsonld(file_path: Path, payloads: list[dict]) -> None:
    """Reemplaza lo que haya entre `JSONLD:START` y `JSONLD:END` con
    los nuevos bloques. Si los marcadores no existen, no toca nada.
    """
    if not file_path.exists():
        return
    text = file_path.read_text(encoding="utf-8")
    new_text, count = _JSONLD_BLOCK_RE.subn(_wrap_jsonld_marker(payloads), text)
    if count:
        file_path.write_text(new_text, encoding="utf-8")


def write_static_jsonld(machines: list[dict]) -> None:
    """Inyecta JSON-LD enriquecido en las páginas estáticas:
    introduction (WebSite + FAQPage), creditos (ItemList de Persons),
    roadmap-oscp (Course).
    """
    for lang in ALL_LANGS:
        intro = _docs_root(lang) / "introduction.mdx"
        _inject_jsonld(
            intro,
            [
                _website_jsonld(lang),
                _faqpage_jsonld(_FAQ_EN if lang == "en" else _FAQ_ES, lang),
            ],
        )
        credits_name = "credits.mdx" if lang == "en" else "creditos.mdx"
        _inject_jsonld(
            _docs_root(lang) / credits_name,
            [_persons_jsonld(lang)],
        )
        _inject_jsonld(
            _docs_root(lang) / "roadmap-oscp.mdx",
            [_course_jsonld(lang)],
        )


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
        "es": ["introduction", "como-usar", "sobre", "creditos"],
        "en": ["en/introduction", "en/how-to-use", "en/about", "en/credits"],
    }[lang]
    catalog_pages = [
        f"{prefix}all",
        f"{prefix}recientes",
        f"{prefix}roadmap-oscp",
        f"{prefix}cobertura-autores",
    ]

    catalog_label = "Catálogo" if lang == "es" else "Catalog"
    tabs = [
        {
            "tab": home_groups_label[0],
            "icon": "house",
            "groups": [
                {"group": home_groups_label[1], "pages": home_pages_label},
                {"group": catalog_label, "pages": catalog_pages},
            ],
        }
    ]

    OS_ICON = {"Linux": "terminal", "Windows": "windows", "Other": "server"}
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
        tabs.append({
            "tab": os_label[os_name],
            "icon": OS_ICON.get(os_name, "circle"),
            "groups": groups,
        })

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

    # Analytics: Mintlify soporta nativo Plausible, GA4, PostHog, etc.
    # Para Cloudflare Web Analytics (gratis), añade tu token desde el
    # panel Mintlify → Settings → Add-ons (no se configura aquí).
    integrations: dict = {}
    plausible_domain = os.environ.get("PLAUSIBLE_DOMAIN", "")
    if plausible_domain:
        integrations["plausible"] = {"domain": plausible_domain}
    ga4_id = os.environ.get("GA4_MEASUREMENT_ID", "")
    if ga4_id:
        integrations["ga4"] = {"measurementId": ga4_id}

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
        # Mintlify sólo sirve los assets que referencia internamente.
        # El resto de variantes se publican vía GitHub raw para que
        # Apple/Android los puedan resolver desde sus User-Agents.
        "metadata": {
            "og:title": "HTB Writeups Hub — rootea.es",
            "og:description": (
                "Directorio curado de writeups de máquinas retiradas de "
                "Hack The Box. Más de 200 máquinas, 5 autores en lista "
                "blanca y enlaces verificados HTTP."
            ),
            "og:image": (
                "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                "main/docs/logo/og.png"
            ),
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
            "twitter:image": (
                "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                "main/docs/logo/og.png"
            ),
            "theme-color": "#9FEF00",
            "robots": "index,follow,max-image-preview:large,max-snippet:-1",
            "keywords": (
                "hack the box, htb, writeups, ctf, s4vitar, ippsec, 0xdf, "
                "pentest, ciberseguridad, oscp, retired machines"
            ),
            "author": "rootea.es",
            # Apple & Android touch icons (servidos desde GitHub raw)
            "apple-mobile-web-app-title": "rootea.es",
            "application-name": "rootea.es",
            "msapplication-TileColor": "#0A0E0A",
        },
        # `head` permite inyectar tags arbitrarios al <head> del HTML
        # generado por Mintlify. Aquí declaramos los iconos PNG en
        # tamaños múltiples para que resuelvan en cada plataforma.
        "head": [
            {
                "tag": "link",
                "attributes": {
                    "rel": "icon",
                    "type": "image/png",
                    "sizes": "32x32",
                    "href": (
                        "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                        "main/docs/logo/favicon-32x32.png"
                    ),
                },
            },
            {
                "tag": "link",
                "attributes": {
                    "rel": "icon",
                    "type": "image/png",
                    "sizes": "16x16",
                    "href": (
                        "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                        "main/docs/logo/favicon-16x16.png"
                    ),
                },
            },
            {
                "tag": "link",
                "attributes": {
                    "rel": "apple-touch-icon",
                    "sizes": "180x180",
                    "href": (
                        "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                        "main/docs/logo/apple-touch-icon.png"
                    ),
                },
            },
            {
                "tag": "link",
                "attributes": {
                    "rel": "manifest",
                    "href": (
                        "https://raw.githubusercontent.com/FFuson/HTB_Writeups/"
                        "main/docs/logo/site.webmanifest"
                    ),
                },
            },
            # hreflang globales (sitewide). Mintlify Hobby no permite
            # per-page hreflang, pero estos marcan a Google la
            # existencia de las dos versiones idiomáticas.
            {
                "tag": "link",
                "attributes": {
                    "rel": "alternate",
                    "hreflang": "es",
                    "href": "https://rootea.es/",
                },
            },
            {
                "tag": "link",
                "attributes": {
                    "rel": "alternate",
                    "hreflang": "en",
                    "href": "https://rootea.es/en",
                },
            },
            {
                "tag": "link",
                "attributes": {
                    "rel": "alternate",
                    "hreflang": "x-default",
                    "href": "https://rootea.es/",
                },
            },
            # Custom CSS y JS de rootea servidos vía jsdelivr (sin
            # cuenta CDN propia). El parámetro `v=N` rompe cache de
            # jsdelivr cuando hace falta forzar refresh.
            {
                "tag": "link",
                "attributes": {
                    "rel": "stylesheet",
                    "href": (
                        "https://cdn.jsdelivr.net/gh/FFuson/HTB_Writeups@main/"
                        "docs/logo/custom.css"
                    ),
                },
            },
            {
                "tag": "script",
                "attributes": {
                    "src": (
                        "https://cdn.jsdelivr.net/gh/FFuson/HTB_Writeups@main/"
                        "docs/logo/custom.js"
                    ),
                    "defer": "",
                },
            },
        ],
        "navigation": {"languages": languages},
        "footer": {
            "socials": {
                "github": "https://github.com/FFuson/HTB_Writeups",
            },
            "links": [
                {
                    "header": "Catálogo",
                    "items": [
                        {"label": "Todas las máquinas", "href": "/all"},
                        {"label": "Recién retiradas", "href": "/recientes"},
                        {"label": "Roadmap OSCP", "href": "/roadmap-oscp"},
                        {"label": "Cobertura por autor", "href": "/cobertura-autores"},
                        {"label": "Máquina aleatoria", "href": "/random"},
                    ],
                },
                {
                    "header": "Autores",
                    "items": [
                        {"label": "S4vitar", "href": "https://www.youtube.com/@s4vitar"},
                        {"label": "El Pingüino de Mario", "href": "https://elpinguinodemario.com"},
                        {"label": "Securízame", "href": "https://www.securizame.com"},
                        {"label": "0xdf", "href": "https://0xdf.gitlab.io"},
                        {"label": "IppSec", "href": "https://ippsec.rocks"},
                    ],
                },
                {
                    "header": "Proyecto",
                    "items": [
                        {"label": "GitHub", "href": "https://github.com/FFuson/HTB_Writeups"},
                        {"label": "RSS feed", "href": "/feed.xml"},
                        {"label": "API JSON", "href": "/api/machines.json"},
                        {"label": "Contribuir", "href": "https://github.com/FFuson/HTB_Writeups/blob/main/CONTRIBUTING.md"},
                        {"label": "Licencia MIT", "href": "https://github.com/FFuson/HTB_Writeups/blob/main/LICENSE"},
                    ],
                },
            ],
        },
    }
    if integrations:
        base["integrations"] = integrations
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
            write_machine_file(m, lang, all_machines=machines)
        write_index_file(machines, lang)
        write_category_indexes(machines, lang)
        write_recent_file(machines, lang)
        write_author_coverage(machines, lang)

    write_intro_stats(machines)
    write_static_jsonld(machines)
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
