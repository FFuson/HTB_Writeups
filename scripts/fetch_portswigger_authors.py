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


# ---------------------------------------------------------------------------
# Configuración de autores
# ---------------------------------------------------------------------------

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
        # Patrón "<Topic> - Lab #N <lab name>"
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
        # z3nsh3ll no usa "Lab #N", título = lab name + sufijos opcionales.
        "strip_prefix_re": None,
        # Sufijos: "- BlackArch/Burp", "- BlackArch", "- Burp Suite", etc.
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
    Maneja abreviaturas comunes para mejorar el matching."""
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
    ]
    for pat, repl in abbreviations:
        text = re.sub(pat, repl, text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
) -> dict | None:
    """labs_index = [(normalized_name, lab), ...]. Devuelve el lab matcheado
    o None.

    Estrategia: substring estricto primero (gana el más largo), Jaccard
    ≥ 0.7 como fallback.
    """
    extracted = _extract_lab_name(video_title, cfg)
    n_video = _normalize(extracted)
    if not n_video:
        return None

    best_strict: tuple[int, dict] | None = None
    best_overlap: tuple[float, dict] | None = None
    for n_lab, lab in labs_index:
        if not n_lab:
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
            for v in videos:
                video_url = f"https://youtu.be/{v['id']}"
                lab = match_video_to_lab(v["title"], cfg, labs_index)
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
        f"[ps-authors] TOTAL: {grand_matched}/{grand_videos} videos "
        f"matched · {n_with_any_extra}/{len(labs)} labs con writeup "
        f"de algún autor whitelist"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
