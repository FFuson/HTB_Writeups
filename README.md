# HTB Writeups Hub

Directorio curado de writeups de **máquinas retiradas** de Hack The
Box, con enlaces a recursos didácticos por skill (HackTricks,
GTFOBins, PortSwigger, Exploit-DB...). No clonamos contenido:
agregamos enlaces verificados hacia los autores originales.

> Si una máquina sigue activa en HTB, **no** aparece aquí. Los TOS
> prohíben publicar pistas de máquinas activas y este proyecto los
> respeta.

## Estado actual

- **203 máquinas** (catálogo completo de HTBMachines, congelado en
  2022-12; las posteriores requieren `HTB_API_TOKEN` opcional).
- **5 autores en lista blanca** — S4vitar, El Pingüino de Mario,
  Securízame, 0xdf, IppSec.
- **32 skills curadas** mapeadas a recursos fiables vía
  `data/skills_glossary.json`.
- Caché en disco (TTL 3-7 días) para YouTube, sitemaps y validación
  HTTP — un run completo cabe en menos de 30 segundos tras la
  primera ejecución.

## Arquitectura

Cinco fases secuenciales, cada una con un script independiente:

```
data/seed_machines.json + data/skills_glossary.json
        │
        ▼
[1] fetch_machines.py   ── HTB API (opcional) + HTBMachines + seed
        │
        ▼
[2] find_writeups.py    ── ippsec.rocks, 0xdf sitemap, scraper YouTube
        │
        ▼
[3] find_skills.py      ── matchea skills contra el glosario curado
        │
        ▼
[4] validate_links.py   ── HEAD requests; descarta 404/timeout
        │
        ▼
[5] generate_mdx.py     ── escupe `.mdx`, `/all`, stats y `docs.json`
        │
        ▼
   Mintlify dev / build
```

Las fases se pueden lanzar sueltas para depurar (`python3 -m
scripts.X`) o encadenadas con `python3 -m scripts.pipeline`.

## Filosofía de calidad

- **Lista blanca de autores.** Sólo se consultan dominios
  declarados en `scripts/config.py`.
- **Validación activa.** Antes de generar el `.mdx`, cada URL recibe
  un `HEAD`. Las que no devuelvan 2xx/3xx se descartan en silencio.
- **Idioma preferente.** Cuando una máquina tiene writeup en español,
  se ordena primero.
- **Sin contenido propio.** El copyright lo tiene el autor; sólo
  enlazamos.
- **Determinismo.** El sort de writeups y el output `.mdx` no
  dependen de orden de iteración.

## Setup

### Requisitos

- Python 3.10+
- Node.js 18+ (sólo para previsualizar Mintlify)

### Instalación

```bash
# Dependencias Python (gestionadas vía pyproject.toml)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# CLI de Mintlify (sólo para preview local)
cd docs && npm install --save-dev mint
```

> No hay `requirements.txt`. Las dependencias viven en `pyproject.toml`
> (sección `[project]` y extras `[dev]` con pytest).

> En macOS sólo viene `python3`; el binario `python` no existe por
> defecto. Si no quieres usar venv, llama a los scripts con `python3`.

### Ejecutar el pipeline

```bash
# Pipeline completo
python3 -m scripts.pipeline

# Suelto (cada fase es independiente, dependen por la salida en disco)
python3 -m scripts.fetch_machines
python3 -m scripts.find_writeups
python3 -m scripts.find_skills
python3 -m scripts.validate_links
python3 -m scripts.generate_mdx
```

Si tienes token de la API de HTB, expórtalo antes para añadir
máquinas posteriores a 2022-12 al catálogo:

```bash
export HTB_API_TOKEN="..."
```

### Previsualizar Mintlify

```bash
cd docs
npx mint dev
```

Abre <http://localhost:3000>. La página `/all` lleva la tabla
maestra de todo el catálogo.

### Tests

```bash
python3 -m unittest discover tests
```

## Estructura de carpetas

```
HTB_Writeups/
├── pyproject.toml
├── data/
│   ├── seed_machines.json       # Semilla fija (commit-eada)
│   ├── skills_glossary.json     # Mapa skill → recursos
│   ├── machines.json            # Salida del pipeline (gitignored)
│   └── _cache/                  # Caché HTTP (gitignored)
├── scripts/
│   ├── cache.py                 # Cache JSON con TTL
│   ├── config.py                # Whitelist de autores y dominios
│   ├── fetch_machines.py        # Fase 1
│   ├── find_writeups.py         # Fase 2
│   ├── find_skills.py           # Fase 3
│   ├── validate_links.py        # Fase 4
│   ├── generate_mdx.py          # Fase 5
│   └── pipeline.py              # Orquestador
├── tests/                       # Unit tests (parsers críticos)
└── docs/                        # Proyecto Mintlify
    ├── docs.json
    ├── introduction.mdx
    ├── como-usar.mdx
    ├── creditos.mdx
    ├── all.mdx                  # Tabla maestra (auto-regenerada)
    └── machines/
        ├── linux/{facil,medio,dificil,insano}/
        ├── windows/{facil,medio,dificil,insano}/
        └── otros/{facil,medio,dificil,insano}/
```

## Cómo añadir cosas

### Nuevo autor a la lista blanca

Edita `scripts/config.py` → diccionario `AUTHORS`. Si el descubrimiento
de URLs no es trivial (sitemap, API, etc.), añade un finder en
`scripts/find_writeups.py`.

### Nueva skill al glosario

Edita `data/skills_glossary.json`. Añade aliases en cualquier idioma
para que el matcher detecte más variantes de la misma skill.

## Mantenimiento

Ejecutar el pipeline una vez por semana basta:

```bash
python3 -m scripts.pipeline && cd docs && npx mint dev
```

El pipeline es idempotente: re-ejecutarlo añade máquinas nuevas y
limpia URLs que dejaron de funcionar.
