"""Matchea videos de YouTube con labs de PortSwigger Web Security
Academy para autores curados.

Cada autor tiene un set de playlists por topic, y un formato de título
ligeramente distinto. La matching logic es la misma:
    1. Extraer el lab name del título (strip prefijo "Lab #N", suffix
       de canal, etc. — configurable por autor).
    2. Match estricto: lab name normalizado ⊆ título normalizado.
    3. Fallback Jaccard ≥ 70% para títulos truncados.

Autores actuales (en lista blanca):
    - Rana Khalil — playlists "Short Version", 9 topics PortSwigger.
    - z3nsh3ll — channel free, 13 topics PortSwigger.

Para añadir un autor nuevo: edita AUTHOR_CONFIGS y describe sus
playlists + opcionalmente regex de strip-prefix/suffix.

Salida: actualiza `data/portswigger_labs.json` in-place añadiendo
entradas writeup. Idempotente: skip si la URL ya existe en lab.writeups.

Cacheado de yt-dlp: 30 días (videos cambian poco).

Requisitos: pip install yt-dlp
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from scripts.cache import JsonCache
from scripts.config import DATA_DIR

PORTSWIGGER_LABS_FILE = DATA_DIR / "portswigger_labs.json"
PORTSWIGGER_OVERRIDES_FILE = DATA_DIR / "portswigger_writeup_overrides.json"


# ---------------------------------------------------------------------------
# Configuración de autores
# ---------------------------------------------------------------------------

# Mapeo display-name → topic_id de PortSwigger. Cada playlist se
# circunscribe al topic_id correspondiente para evitar que un video
# matchee a un lab de OTRO topic (caso real: "Directory Traversal"
# matcheaba con "Web shell upload via path traversal" porque
# comparten 'path traversal' como tokens).
PLAYLIST_TOPIC_ID = {
    "SQL Injection":             "sql-injection",
    "Authentication":            "authentication",
    "Directory Traversal":       "file-path-traversal",
    "Broken Access Control":     "access-control",
    "Broken Access control":     "access-control",
    "Command Injection":         "os-command-injection",
    "OS Command Injection":      "os-command-injection",
    "CORS":                      "cors",
    "SSRF":                      "ssrf",
    "CSRF":                      "csrf",
    "Business Logic":            "logic-flaws",
    "XSS":                       "cross-site-scripting",
    "Information Disclosure":    "information-disclosure",
    "Dom Vulnerabilities":       "dom-based",
    "WebSockets":                "websockets",
    "OAuth":                     "oauth",
    "JWT":                       "jwt",
    "XXE":                       "xxe",
    "GraphQL":                   "graphql",
    "Race Conditions":           "race-conditions",
    "File Upload":               "file-upload",
    "Web Cache Poisoning":       "web-cache-poisoning",
    "Web Cache Deception":       "web-cache-deception",
    "Insecure Deserialization":  "deserialization",
    "Prototype Pollution":       "prototype-pollution",
    "HTTP Host Header Attacks":  "host-header",
    "API Testing":               "api-testing",
    "Clickjacking":              "clickjacking",
    "Server-Side Template Injection": "server-side-template-injection",
    "LLM Attacks":               "llm-attacks",
    "NoSQL Injection":           "nosql-injection",
    "Request Smuggling":         "request-smuggling",
}


AUTHOR_CONFIGS: dict[str, dict] = {
    "Rana Khalil": {
        "language": "EN",
        "format": "Vídeo",
        # Playlists "Short Version" — un video por lab, focalizado.
        "playlists": [
            ("SQL Injection",            "PLuyTk2_mYISItkbigDRkL9BFpyRenqrRJ"),
            ("Authentication",           "PLuyTk2_mYISIZICCCdK7sLjKN1s1z9OQi"),
            ("Directory Traversal",      "PLuyTk2_mYISIoeOc9KdGzxTTD36otd8I_"),
            ("Broken Access Control",    "PLuyTk2_mYISJxFXJDdkDZjXD4K1yl3NFU"),
            ("Command Injection",        "PLuyTk2_mYISIP3vpjzVdNltKKUr27Nwtw"),
            ("CORS",                     "PLuyTk2_mYISJpyzYl947x48JABj0AVVUF"),
            ("SSRF",                     "PLuyTk2_mYISIA-OkiXfOFn1NM0JNULAHO"),
            ("CSRF",                     "PLuyTk2_mYISKn1UzXAFl_DA3MaEJ9J-yq"),
            ("Business Logic",           "PLuyTk2_mYISICvn92w-wsflDLpXqHwLQX"),
        ],
        "strip_prefix_re": re.compile(r"^.*?-\s*Lab\s*#?\d+\s+", re.IGNORECASE),
        "strip_suffix_re": None,
    },
    "z3nsh3ll": {
        "language": "EN",
        "format": "Vídeo",
        "playlists": [
            ("SQL Injection",            "PLWvfB8dRFqba0CSHMY23ih0tUNrK9iEJv"),
            ("XSS",                      "PLWvfB8dRFqbZG5cw2OrnEmzSzorxRuxFV"),
            ("CSRF",                     "PLWvfB8dRFqbYxXt98916MC_qFxv9dQ2xV"),
            ("SSRF",                     "PLWvfB8dRFqbYomXQJ4Im_m1_-GgG6FulK"),
            ("Directory Traversal",      "PLWvfB8dRFqbbO2wRawnn6u8JlfttA74wE"),
            ("Authentication",           "PLWvfB8dRFqbbwmsFZg4vEkOxv9KmFCHrJ"),
            ("Broken Access control",    "PLWvfB8dRFqba6RlegailkE8ENfyjWc4dZ"),
            ("OS Command Injection",     "PLWvfB8dRFqbZgHcGZSKIidV18GeUIVTHF"),
            ("Business Logic",           "PLWvfB8dRFqbYDNDvmDlGgM-UTRGpCyKQ1"),
            ("Information Disclosure",   "PLWvfB8dRFqbYoGa4eFkAqiJKAF7CnIVlR"),
            ("Dom Vulnerabilities",      "PLWvfB8dRFqba4RedkuUDWMEkAkP8cdZCW"),
            ("WebSockets",               "PLWvfB8dRFqbb-wxFtexld1yFszX-JID3R"),
            ("OAuth",                    "PLWvfB8dRFqbam3mm6yJ47VYEfeqg1tGS-"),
        ],
        "strip_prefix_re": None,
        "strip_suffix_re": re.compile(
            r"\s*[-|]\s*(BlackArch/Burp|BlackArch|Burp Suite|Burp Pro|Burp|"
            r"Web Security Academy|PortSwigger).*$",
            re.IGNORECASE,
        ),
    },
}


# ---------------------------------------------------------------------------
# YouTube playlist fetcher (cached)
# ---------------------------------------------------------------------------

_yt_cache = JsonCache("portswigger_authors_playlists", ttl_days=30)


def fetch_playlist_videos(playlist_id: str) -> list[dict]:
    cached = _yt_cache.get(playlist_id)
    if cached is not None:
        return cached

    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-single-json",
                "--no-warnings",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(
            f"[ps-authors] yt-dlp falló para {playlist_id}: {exc}",
            file=sys.stderr,
        )
        return []
    if result.returncode != 0:
        print(
            f"[ps-authors] yt-dlp rc={result.returncode} para {playlist_id}: "
            f"{result.stderr[:200]}",
            file=sys.stderr,
        )
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    videos = [
        {"id": e.get("id"), "title": (e.get("title") or "").strip()}
        for e in data.get("entries", [])
        if e.get("id") and e.get("title")
    ]
    _yt_cache.set(playlist_id, videos)
    return videos


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase + alphanumérico-solo + colapsa whitespace.
    Maneja abreviaturas y sinónimos comunes para mejorar el matching."""
    text = text.lower()
    abbreviations = [
        (r"\bsqli\b", "sql injection"),
        (r"\bxss\b", "cross site scripting"),
        (r"\bssrf\b", "server side request forgery"),
        (r"\bxxe\b", "xml external entity"),
        (r"\bcsrf\b", "cross site request forgery"),
        (r"\bcors\b", "cross origin resource sharing"),
        (r"\&", " and "),
        (r"\bdom\b", "dom based"),
        (r"\bw/\b", "with"),
        (r"\bw\.\s+", "with "),
        # Sinónimos topic-level: PortSwigger usa "file path traversal"
        # pero z3nsh3ll y otros usan "directory traversal" indistintamente.
        (r"\bdirectory traversal\b", "file path traversal"),
        # "non-recursive" ↔ "non recursively"
        (r"\bnon[-\s]recursive\b", "non recursively"),
    ]
    for pat, repl in abbreviations:
        text = re.sub(pat, repl, text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Stopwords + verbos comunes que NO discriminan entre labs.
_NOISE_TOKENS = frozenset({
    "a", "an", "the", "of", "to", "for", "with", "in", "on", "by",
    "from", "and", "or", "but", "is", "are", "be", "this", "that",
    "what", "how", "when", "why", "where", "which", "who", "whom",
    # Verbos genéricos que aparecen en muchos títulos editoriales
    "attack", "exploit", "exploiting", "running", "run", "using",
    "use", "demo", "demonstration", "tutorial", "vulnerability",
    "vulnerable", "vulnerabilities", "video", "lab", "labs",
    # Generales
    "into", "via", "without", "between",
})


def _build_topic_tokens(labs: list[dict]) -> dict[str, set[str]]:
    """Para cada topic, calcula los tokens que aparecen en TODOS sus
    labs (intersección). Esos tokens NO discriminan entre labs del
    mismo topic — son los que excluimos al calcular el anchor score.

    Solo aplica a topics con ≥ 3 labs; con < 3 la intersección
    captura demasiado y arruina el matching.
    """
    by_topic: dict[str, list[set[str]]] = {}
    for l in labs:
        tid = l.get("topic_id") or "misc"
        by_topic.setdefault(tid, []).append(set(_normalize(l["name"]).split()))
    out: dict[str, set[str]] = {}
    for tid, token_lists in by_topic.items():
        if len(token_lists) < 3:
            out[tid] = set()
            continue
        common = token_lists[0].copy()
        for tl in token_lists[1:]:
            common &= tl
        out[tid] = common
    return out


def _distinctive_tokens(
    lab: dict, topic_tokens: set[str]
) -> set[str]:
    """Tokens del lab name que NO son ni topic-tokens ni noise."""
    tokens = set(_normalize(lab["name"]).split())
    return tokens - topic_tokens - _NOISE_TOKENS


def _anchor_score(
    video_norm: str, lab: dict, topic_tokens: set[str]
) -> tuple[float, int]:
    """Devuelve (fracción cubierta, n_tokens_matched). Mide qué fracción
    de tokens distintivos del lab aparecen en el video título normalizado.
    """
    distinctive = _distinctive_tokens(lab, topic_tokens)
    if not distinctive:
        return 0.0, 0
    video_set = set(video_norm.split())
    matched = distinctive & video_set
    return len(matched) / len(distinctive), len(matched)


def _extract_lab_name(title: str, cfg: dict) -> str:
    if cfg.get("strip_prefix_re"):
        title = cfg["strip_prefix_re"].sub("", title).strip()
    if cfg.get("strip_suffix_re"):
        title = cfg["strip_suffix_re"].sub("", title).strip()
    title = re.sub(r"^Lab\s*\d+\s*[:\-]?\s*", "", title, flags=re.IGNORECASE)
    return title.strip()


def _token_overlap(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())
    if not sb:
        return 0.0
    return len(sa & sb) / len(sb)


def match_video_to_lab(
    video_title: str,
    cfg: dict,
    labs_index: list[tuple[str, dict]],
    topic_tokens_map: dict[str, set[str]] | None = None,
    restrict_topic_id: str | None = None,
) -> dict | None:
    """labs_index = [(normalized_name, lab), ...]. Devuelve el lab matcheado
    o None.

    Estrategia (en orden, gana el primero que dispara):
      1. Substring estricto: lab name normalized ⊆ video title normalized.
         Si varios matchean, gana el más largo.
      2. Jaccard ≥ 0.7 sobre tokens. Cubre títulos truncados.
      3. Anchor score ≥ 0.6 + ≥ 2 tokens distintivos en común. Para
         títulos editoriales que reformulan el lab name. SOLO se aplica
         si `restrict_topic_id` está poblado (limita el matching al
         topic del playlist, evitando cross-topic false positives).

    Si `restrict_topic_id` se provee, los pasos 1 y 2 también se
    restringen a ese topic. Solo se desactiva la restricción para
    autores con playlists indistintas.
    """
    extracted = _extract_lab_name(video_title, cfg)
    n_video = _normalize(extracted)
    if not n_video:
        return None

    def _in_scope(lab: dict) -> bool:
        if restrict_topic_id is None:
            return True
        return lab.get("topic_id") == restrict_topic_id

    best_strict: tuple[int, dict] | None = None
    best_overlap: tuple[float, dict] | None = None
    for n_lab, lab in labs_index:
        if not n_lab or not _in_scope(lab):
            continue
        if n_lab in n_video:
            score = len(n_lab)
            if best_strict is None or score > best_strict[0]:
                best_strict = (score, lab)
        else:
            ov = _token_overlap(n_video, n_lab)
            if ov >= 0.7:
                if best_overlap is None or ov > best_overlap[0]:
                    best_overlap = (ov, lab)

    if best_strict is not None:
        return best_strict[1]
    if best_overlap is not None:
        return best_overlap[1]

    # Fallback 3: anchor-based scoring (topic-restricted obligatorio).
    if topic_tokens_map is None or restrict_topic_id is None:
        return None
    best_anchor: tuple[float, int, dict] | None = None
    for n_lab, lab in labs_index:
        if not _in_scope(lab):
            continue
        topic_tokens = topic_tokens_map.get(lab.get("topic_id", ""), set())
        score, n_matched = _anchor_score(n_video, lab, topic_tokens)
        if score >= 0.6 and n_matched >= 2:
            if best_anchor is None or score > best_anchor[0]:
                best_anchor = (score, n_matched, lab)
    if best_anchor is not None:
        return best_anchor[2]

    return None


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def main() -> int:
    if not PORTSWIGGER_LABS_FILE.exists():
        print(
            f"[ps-authors] {PORTSWIGGER_LABS_FILE} no existe. "
            f"Ejecuta antes scripts.fetch_portswigger.",
            file=sys.stderr,
        )
        return 1

    labs = json.loads(PORTSWIGGER_LABS_FILE.read_text(encoding="utf-8"))
    labs_index = [(_normalize(l["name"]), l) for l in labs]
    topic_tokens_map = _build_topic_tokens(labs)

    grand_videos = 0
    grand_matched = 0

    for author, cfg in AUTHOR_CONFIGS.items():
        author_videos = 0
        author_matched = 0
        # Limpieza idempotente: borrar entradas previas de este autor.
        for l in labs:
            l["writeups"] = [
                w for w in l.get("writeups", [])
                if w.get("autor") != author
            ]

        per_topic_stats: dict[str, dict[str, int]] = {}
        for topic, playlist_id in cfg["playlists"]:
            videos = fetch_playlist_videos(playlist_id)
            stats = {"videos": len(videos), "matched": 0}
            author_videos += len(videos)
            # Restringir matching al topic del playlist (resuelve falsos
            # positivos cross-topic — p.ej. video de Directory Traversal
            # matcheando con un lab de file-upload).
            scope_topic_id = PLAYLIST_TOPIC_ID.get(topic)
            if scope_topic_id is None:
                print(
                    f"[ps-authors]   ⚠ playlist '{topic}' no mapea a topic_id; "
                    f"matching sin restricción.",
                    file=sys.stderr,
                )
            for v in videos:
                video_url = f"https://youtu.be/{v['id']}"
                lab = match_video_to_lab(
                    v["title"], cfg, labs_index, topic_tokens_map,
                    restrict_topic_id=scope_topic_id,
                )
                if not lab:
                    continue
                stats["matched"] += 1
                author_matched += 1
                existing_urls = {w.get("url") for w in lab.get("writeups", [])}
                if video_url in existing_urls:
                    continue
                lab.setdefault("writeups", []).append({
                    "autor": author,
                    "idioma": cfg["language"],
                    "formato": cfg["format"],
                    "url": video_url,
                })
            per_topic_stats[topic] = stats

        n_with_author = sum(
            1 for l in labs
            if any(w.get("autor") == author for w in l.get("writeups", []))
        )
        print(
            f"[ps-authors] {author}: {author_matched}/{author_videos} "
            f"videos matched · {n_with_author}/{len(labs)} labs cubiertos"
        )
        for topic, st in per_topic_stats.items():
            ratio = st["matched"] * 100 // max(st["videos"], 1)
            print(
                f"  {topic:30s} {st['matched']:>3}/{st['videos']:<3} "
                f"({ratio}%)"
            )
        grand_videos += author_videos
        grand_matched += author_matched

    _yt_cache.save()

    # Aplicar overrides manuales — para casos donde el matcher
    # automático honesto no puede inferir el lab sin riesgo de falsos
    # positivos (títulos editoriales, abreviaturas no estándar, labs
    # retirados, etc.). Cada override se valida contra los labs
    # actuales; si el lab_id no existe se reporta y se ignora.
    overrides_applied = _apply_manual_overrides(labs)
    if overrides_applied:
        print(
            f"[ps-authors] manual overrides: {overrides_applied} entradas "
            f"aplicadas desde {PORTSWIGGER_OVERRIDES_FILE.name}"
        )

    PORTSWIGGER_LABS_FILE.write_text(
        json.dumps(labs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_with_any_extra = sum(
        1 for l in labs
        if any(
            w.get("autor") in AUTHOR_CONFIGS
            for w in l.get("writeups", [])
        )
    )
    print(
        f"[ps-authors] TOTAL: {grand_matched + overrides_applied} videos "
        f"matched (auto: {grand_matched} + override: {overrides_applied}) · "
        f"{n_with_any_extra}/{len(labs)} labs con writeup "
        f"de algún autor whitelist"
    )
    return 0


def _apply_manual_overrides(labs: list[dict]) -> int:
    """Lee `data/portswigger_writeup_overrides.json` y añade las
    entradas {video_url, lab_id, author, language, format} a los
    writeups del lab correspondiente. Idempotente: skip si la URL
    ya existe en lab.writeups.
    """
    if not PORTSWIGGER_OVERRIDES_FILE.exists():
        return 0
    try:
        data = json.loads(PORTSWIGGER_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"[ps-authors] overrides corruptos: {exc}", file=sys.stderr
        )
        return 0
    overrides = data.get("overrides", [])
    if not overrides:
        return 0
    labs_by_id = {l["id"]: l for l in labs}
    applied = 0
    for o in overrides:
        lab_id = o.get("lab_id")
        url = o.get("video_url")
        if not lab_id or not url:
            continue
        lab = labs_by_id.get(lab_id)
        if lab is None:
            print(
                f"[ps-authors] override: lab_id {lab_id!r} no existe — "
                f"skip {url}",
                file=sys.stderr,
            )
            continue
        existing_urls = {w.get("url") for w in lab.get("writeups", [])}
        if url in existing_urls:
            continue
        lab.setdefault("writeups", []).append({
            "autor": o.get("author", "Unknown"),
            "idioma": o.get("language", "EN"),
            "formato": o.get("format", "Vídeo"),
            "url": url,
        })
        applied += 1
    return applied


if __name__ == "__main__":
    sys.exit(main())
