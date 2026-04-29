"""Lista blanca de autores de writeups y configuración global del pipeline.

Toda decisión sobre qué autores entran en el directorio se toma aquí. Si
un autor no aparece en `WHITELIST_DOMAINS`, el resto del pipeline lo
ignora aunque algún descubridor lo encuentre.
"""

from __future__ import annotations

from pathlib import Path

# --- Rutas del proyecto -----------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
MACHINES_DIR = DOCS_DIR / "machines"
SEED_FILE = DATA_DIR / "seed_machines.json"
MACHINES_FILE = DATA_DIR / "machines.json"
DOCS_JSON = DOCS_DIR / "docs.json"

# --- Autores aceptados ------------------------------------------------------
# Cada entrada describe a un autor: nombre canónico, idioma, formato por
# defecto, y los dominios desde los que aceptamos URLs suyas.

AUTHORS: dict[str, dict] = {
    "S4vitar": {
        "idioma": "ES",
        "formato": "Vídeo",
        "dominios": ["youtube.com", "youtu.be", "hackmind.es"],
        "homepage": "https://www.youtube.com/@s4vitar",
    },
    "El Pingüino de Mario": {
        "idioma": "ES",
        "formato": "Texto",
        "dominios": ["elpinguinodemario.com"],
        "homepage": "https://elpinguinodemario.com",
    },
    "Securízame": {
        "idioma": "ES",
        "formato": "Texto",
        "dominios": ["securizame.com", "blog.securizame.com"],
        "homepage": "https://www.securizame.com",
    },
    "0xdf": {
        "idioma": "EN",
        "formato": "Texto",
        "dominios": ["0xdf.gitlab.io"],
        "homepage": "https://0xdf.gitlab.io",
    },
    "IppSec": {
        "idioma": "EN",
        "formato": "Vídeo",
        "dominios": ["ippsec.rocks", "youtube.com", "youtu.be"],
        "homepage": "https://ippsec.rocks",
    },
}

# Dominios autorizados (derivado plano)
WHITELIST_DOMAINS: set[str] = {
    domain
    for author in AUTHORS.values()
    for domain in author["dominios"]
}

# Recursos de skills/glosario. Distintos de WHITELIST_DOMAINS porque
# aquí no estamos pidiendo "writeup del autor X", sino "documentación
# de la técnica Y". Aceptamos un conjunto independiente.
SKILL_DOMAINS: set[str] = {
    "book.hacktricks.wiki",
    "book.hacktricks.xyz",
    "hacktricks.boitatech.com.br",
    "gtfobins.github.io",
    "lolbas-project.github.io",
    "portswigger.net",
    "exploit-db.com",
    "www.exploit-db.com",
    "github.com",
    "raw.githubusercontent.com",
    "bloodhound.specterops.io",
    "docs.pi-hole.net",
}

# Glosario de skills (path al fichero JSON curado)
SKILLS_GLOSSARY = DATA_DIR / "skills_glossary.json"


# --- Mapas de normalización -------------------------------------------------

DIFFICULTY_MAP = {
    "easy": "Fácil",
    "fácil": "Fácil",
    "facil": "Fácil",
    "medium": "Medio",
    "medio": "Medio",
    "media": "Medio",
    "hard": "Difícil",
    "difícil": "Difícil",
    "dificil": "Difícil",
    "insane": "Insano",
    "insano": "Insano",
}

DIFFICULTY_SLUG = {
    "Fácil": "facil",
    "Medio": "medio",
    "Difícil": "dificil",
    "Insano": "insano",
}

OS_SLUG = {
    "Linux": "linux",
    "Windows": "windows",
    "FreeBSD": "otros",
    "OpenBSD": "otros",
    "Solaris": "otros",
    "Other": "otros",
    "": "otros",
}


def normalize_difficulty(value: str) -> str:
    return DIFFICULTY_MAP.get(value.strip().lower(), value.strip() or "Fácil")


def normalize_os(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "Other"
    if v.lower() == "linux":
        return "Linux"
    if v.lower() == "windows":
        return "Windows"
    return v


def os_to_slug(os_name: str) -> str:
    return OS_SLUG.get(os_name, "otros")


def difficulty_to_slug(difficulty: str) -> str:
    return DIFFICULTY_SLUG.get(difficulty, "facil")


# --- Configuración del validador --------------------------------------------

HTTP_TIMEOUT = 10  # segundos
HTTP_CONCURRENCY = 16
USER_AGENT = "htb-writeups-aggregator/1.0 (+https://github.com/quodix)"
