<div align="center">

# HTB Writeups Hub

**Directorio curado de writeups de máquinas retiradas de Hack The Box.**
Bilingüe ES/EN. Enlaces validados. Sin contenido propio.

[![Refresh](https://github.com/FFuson/HTB_Writeups/actions/workflows/refresh.yml/badge.svg)](https://github.com/FFuson/HTB_Writeups/actions/workflows/refresh.yml)
[![Site](https://img.shields.io/website?url=https%3A%2F%2Frootea.es&label=rootea.es&up_color=9FEF00)](https://rootea.es)
[![License: MIT](https://img.shields.io/badge/license-MIT-9FEF00.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Mintlify](https://img.shields.io/badge/docs-Mintlify-9FEF00)](https://mintlify.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/FFuson/HTB_Writeups/pulls)

🌐 **[rootea.es](https://rootea.es)** · 🇪🇸 **[Versión ES](https://rootea.es)** · 🇬🇧 **[English version](https://rootea.es/en)**

</div>

---

## Tabla de contenidos

- [Qué es esto](#qué-es-esto)
- [Filosofía](#filosofía)
- [Capturas](#capturas)
- [Arquitectura](#arquitectura)
- [Setup](#setup)
- [Uso](#uso)
- [Estructura](#estructura)
- [Cómo extender](#cómo-extender)
- [Cómo desplegar](#cómo-desplegar)
- [SEO y SGEO](#seo-y-sgeo)
- [Tests](#tests)
- [Licencia](#licencia)

---

## Qué es esto

Hack The Box (HTB) tiene cientos de máquinas retiradas y la
documentación está repartida entre blogs, vídeos, repos y posts
efímeros. Este proyecto **no clona** nada de eso: **agrega enlaces
verificados** hacia los autores originales y los organiza por sistema
operativo, dificultad y skills requeridas.

| Métrica | Valor actual |
|---|---|
| Máquinas indexadas | 203 |
| Writeups validados | ~600 |
| Recursos didácticos | ~330 |
| Autores en lista blanca | 5 |
| Skills mapeadas | 32 |
| Idiomas | 2 (ES default, EN) |

---

## Filosofía

- **Lista blanca de autores.** Sólo S4vitar, El Pingüino de Mario,
  Securízame, 0xdf e IppSec. Cero relleno SEO.
- **Validación HTTP semanal.** Cada URL recibe `HEAD`. Si devuelve
  4xx/5xx, fuera.
- **Idioma preferente.** Cuando hay writeup en español, sale primero.
- **Sólo retiradas.** Las máquinas activas en HTB jamás aparecen aquí.
- **Sin contenido propio.** El copyright lo tiene el autor; sólo
  enlazamos.
- **Determinismo.** El sort y el output `.mdx` no dependen del orden
  de iteración: dos runs producen el mismo árbol byte a byte.

---

## Capturas

> _Pendiente de añadir capturas reales del sitio en producción
> (`rootea.es`). Por ahora, lo que verás:_

- Home con tarjetas de stats auto-regeneradas (203 máquinas · 615
  writeups · 331 recursos).
- `/all` con tabla maestra ordenada por SO + dificultad + skills
  como chips.
- Página de máquina con metadata, writeups por idioma/autor y
  recursos por skill.
- Selector de idioma ES/EN en navbar (Mintlify nativo).

---

## Arquitectura

Pipeline de **5 fases** secuenciales, cada una un script
independiente y debugueable:

```
data/seed_machines.json + data/skills_glossary.json
        │
        ▼
[1] fetch_machines.py    HTB API (opcional) + HTBMachines + seed
        │
        ▼
[2] find_writeups.py     ippsec.rocks, 0xdf sitemap, scraper YouTube
        │
        ▼
[3] find_skills.py       matchea skills contra glosario curado
        │
        ▼
[4] validate_links.py    HEAD concurrente (Session + Retry)
        │
        ▼
[5] generate_mdx.py      .mdx ES + .mdx EN + JSON-LD + docs.json
        │
        ▼
   Mintlify build → rootea.es
```

Caché en disco con TTL (`data/_cache/`) para sitemaps, scraping de
YouTube y validación HTTP. Tras el primer run, los siguientes
terminan en segundos.

---

## Setup

### Requisitos

- Python 3.10+
- Node.js 18+ (sólo para previsualizar Mintlify localmente)
- `librsvg` (sólo si vas a regenerar la imagen Open Graph)

### Instalación

```bash
git clone https://github.com/FFuson/HTB_Writeups.git
cd HTB_Writeups

# Dependencias Python (gestionadas vía pyproject.toml)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# CLI de Mintlify (opcional, sólo para preview local)
cd docs && npm install --save-dev mint
```

> En macOS sólo viene `python3` por defecto. No hay `requirements.txt`
> — todo vive en `pyproject.toml`.

---

## Uso

```bash
# Pipeline completo
python3 -m scripts.pipeline

# Forzar regeneración ignorando la caché
python3 -m scripts.pipeline --no-cache

# Cada fase es independiente; lanza sólo la que necesites
python3 -m scripts.fetch_machines
python3 -m scripts.find_writeups
python3 -m scripts.find_skills
python3 -m scripts.validate_links
python3 -m scripts.generate_mdx

# Preview local en http://localhost:3000
cd docs && npx mint dev
```

### Variables de entorno

| Variable | Uso |
|---|---|
| `HTB_API_TOKEN` | Token de la API v4 de HTB. Sin él se usa el dataset comunitario. Permite ampliar el catálogo a máquinas posteriores a 2022-12. |

---

## Estructura

```
HTB_Writeups/
├── pyproject.toml
├── LICENSE                          (MIT)
├── data/
│   ├── seed_machines.json           # Semilla fija (commit)
│   ├── skills_glossary.json         # Mapa skill → recursos didácticos
│   ├── machines.json                # Salida del pipeline (gitignored)
│   └── _cache/                      # Caché HTTP (gitignored)
├── scripts/
│   ├── cache.py                     # Cache JSON con TTL
│   ├── changelog.py                 # Diff machines.json → resumen commit
│   ├── config.py                    # Whitelist autores, dominios, locales
│   ├── fetch_machines.py            # Fase 1
│   ├── find_writeups.py             # Fase 2
│   ├── find_skills.py               # Fase 3
│   ├── validate_links.py            # Fase 4
│   ├── generate_mdx.py              # Fase 5
│   └── pipeline.py                  # Orquestador
├── tests/                           # Unit tests sobre parsers críticos
├── .github/workflows/
│   └── refresh.yml                  # Cron semanal de refresh
└── docs/                            # Proyecto Mintlify
    ├── docs.json                    # Auto-generado (incluye nav i18n)
    ├── introduction.mdx
    ├── como-usar.mdx
    ├── creditos.mdx
    ├── all.mdx                      # Tabla maestra del catálogo
    ├── logo/                        # Light/dark/favicon/og.png
    ├── machines/{linux,windows,otros}/{facil,medio,dificil,insano}/
    └── en/                          # Árbol espejo en inglés
```

---

## Cómo extender

### Añadir un autor nuevo

1. Edita `scripts/config.py` → diccionario `AUTHORS`.
2. Si la URL del autor no se descubre por scraping conocido, añade un
   `finder_*` en `scripts/find_writeups.py`.
3. PR con justificación de por qué el material es consistente en
   calidad. **No vale lista de Medium random.**

### Añadir una skill al glosario

1. Edita `data/skills_glossary.json`.
2. Añade aliases en cualquier idioma para que el matcher detecte más
   variantes.
3. Re-ejecuta `python3 -m scripts.find_skills && python3 -m scripts.generate_mdx`.

### Cambiar el sitio

- **Colores / branding**: `scripts/generate_mdx.py:write_docs_json`.
- **Logo**: SVGs en `docs/logo/`. Regenera `og.png` con
  `rsvg-convert -w 1200 -h 630 docs/logo/og.svg -o docs/logo/og.png`.
- **Páginas estáticas**: `docs/{introduction,como-usar,creditos}.mdx`
  (ES) y `docs/en/{introduction,how-to-use,credits}.mdx` (EN).

---

## Cómo desplegar

El sitio se despliega en **Mintlify Hobby (gratis)** conectando este
repo a su panel. La GitHub Action `refresh.yml` corre cada lunes a las
06:00 UTC, regenera el catálogo y commitea — Mintlify detecta el push
y despliega automáticamente.

### Setup inicial del despliegue

1. <https://mintlify.com> → Sign in with GitHub.
2. New Documentation → repo `FFuson/HTB_Writeups`, subdir `docs`.
3. Settings → Domain setup → custom domain (ej. `rootea.es`).
4. DNS: registro `A @ → 76.76.21.21` (gestionado vía Cloudflare).

### Action semanal

`.github/workflows/refresh.yml`:
- Cron lunes 06:00 UTC + `workflow_dispatch` manual.
- Tests unitarios bloqueantes.
- Cache de `data/_cache` persistida con `actions/cache`.
- Soporta `secrets.HTB_API_TOKEN` (opcional).
- Mensaje de commit auto-generado (`scripts.changelog`).

---

## SEO y SGEO

Optimizado para tanto buscadores tradicionales como motores de
búsqueda generativos (ChatGPT, Claude, Perplexity, Gemini):

- **JSON-LD `TechArticle`** en cada página de máquina con
  `inLanguage`, `datePublished`, `dateModified`, `proficiencyLevel`.
- **JSON-LD `CollectionPage` + `ItemList`** en `/all` y `/en/all`.
- **`Última actualización: YYYY-MM-DD`** en cada página (los LLMs
  favorecen contenido fechado).
- **FAQ block** en formato `**Pregunta**\n\nRespuesta` (formato que
  Perplexity y ChatGPT extraen mejor).
- **Disambiguation explícita** primera mención de "Hack The Box (HTB)"
  por página.
- **Open Graph + Twitter Card** completos con imagen `og.png`
  (1200×630).
- **`robots: index,follow,max-image-preview:large,max-snippet:-1`**
  para permitir extracción amplia.
- **Mintlify provee out-of-the-box**: `sitemap.xml`, `robots.txt`,
  `llms.txt`, `llms-full.txt`, canonical tags.

---

## Tests

```bash
python3 -m unittest discover tests
```

Cubren los parsers críticos: extracción JS de htbmachines, escape
MDX, slugify, truncate.

---

## Licencia

[MIT](LICENSE) — © 2026 FFuson

Hack The Box es una marca registrada de Hack The Box Ltd. Este
proyecto **no está afiliado** a HTB ni a ninguno de los autores
listados. Sólo enlaza al material que ellos han publicado abiertamente.

---

<div align="center">

**¿Te ha sido útil?** ⭐ Star este repo y suscríbete a los canales
de los autores originales — sin ellos no hay catálogo.

</div>
