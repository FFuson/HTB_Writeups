"""Fase 3: matching de videos de Rana Khalil con labs de PortSwigger.

Rana Khalil tiene un canal de YouTube con playlists "Short Version"
por topic, donde cada vídeo cubre exactamente un lab de PortSwigger.
El título sigue el patrón:

    "<Topic> - Lab #N <lab title verbatim>"

Estrategia:
    1. Por cada playlist (curada manualmente — Rana cubre 9 topics).
    2. Listar videos vía yt-dlp.
    3. Para cada vídeo, normalizar título + match por substring contra
       los nombres de labs en `data/portswigger_labs.json`.
    4. Añadir el video URL como writeup a cada lab matcheado.

Salida: `data/portswigger_labs.json` se actualiza in-place. Idempotente:
si una entrada de Rana ya existe en `writeups`, no se duplica.

Ejecución: local cuando Rana añada nuevos vídeos. Cacheamos los
resultados de yt-dlp con TTL 30 días para evitar re-fetcheos.

Requisitos:
    pip install yt-dlp
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from scripts.cache import JsonCache
from scripts.config import DATA_DIR

PORTSWIGGER_LABS_FILE = DATA_DIR / "portswigger_labs.json"

# Playlists "Short Version" de Rana Khalil — un video por lab,
# focalizado. Las "Long Version" son educativas, no se mapean 1:1 con
# labs y dejarían los lab pages saturados de duplicados.
RANA_SHORT_PLAYLISTS = [
    ("SQL Injection",            "PLuyTk2_mYISItkbigDRkL9BFpyRenqrRJ"),
    ("Authentication",           "PLuyTk2_mYISIZICCCdK7sLjKN1s1z9OQi"),
    ("Directory Traversal",      "PLuyTk2_mYISIoeOc9KdGzxTTD36otd8I_"),
    ("Broken Access Control",    "PLuyTk2_mYISJxFXJDdkDZjXD4K1yl3NFU"),
    ("Command Injection",        "PLuyTk2_mYISIP3vpjzVdNltKKUr27Nwtw"),
    ("CORS",                     "PLuyTk2_mYISJpyzYl947x48JABj0AVVUF"),
    ("SSRF",                     "PLuyTk2_mYISIA-OkiXfOFn1NM0JNULAHO"),
    ("CSRF",                     "PLuyTk2_mYISKn1UzXAFl_DA3MaEJ9J-yq"),
    ("Business Logic",           "PLuyTk2_mYISICvn92w-wsflDLpXqHwLQX"),
]

_yt_cache = JsonCache("rana_khalil_playlists", ttl_days=30)


def fetch_playlist_videos(playlist_id: str) -> list[dict]:
    """Devuelve [{id, title}] de una playlist YouTube. Cacheado."""
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
            f"[rana] yt-dlp falló para {playlist_id}: {exc}",
            file=sys.stderr,
        )
        return []
    if result.returncode != 0:
        print(
            f"[rana] yt-dlp rc={result.returncode} para {playlist_id}: "
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


# Patrón de título: "<topic> - Lab #N <lab name>" o variantes.
_TITLE_PREFIX_RE = re.compile(
    r"^.*?-\s*Lab\s*#?\d+\s+", re.IGNORECASE
)


def _normalize(text: str) -> str:
    """Lowercase + alphanumérico-solo + colapsa whitespace.
    Maneja abreviaturas comunes para mejorar el matching."""
    text = text.lower()
    # Abreviaturas que Rana usa pero PortSwigger no (o al revés).
    abbreviations = [
        (r"\bsqli\b", "sql injection"),
        (r"\bxss\b", "cross site scripting"),
        (r"\bssrf\b", "server side request forgery"),
        (r"\bxxe\b", "xml external entity"),
        (r"\bcsrf\b", "cross site request forgery"),
        (r"\bcors\b", "cross origin resource sharing"),
        (r"\&", " and "),
    ]
    for pat, repl in abbreviations:
        text = re.sub(pat, repl, text)
    # Normalizar puntuación a espacio
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_lab_name_from_title(video_title: str) -> str:
    """Quita el prefijo '<Topic> - Lab #N ' y devuelve el nombre del lab."""
    cleaned = _TITLE_PREFIX_RE.sub("", video_title).strip()
    # Limpieza adicional de patrones comunes:
    # "Lab1 SQL ..." sin guion ni almohadilla
    cleaned = re.sub(r"^Lab\s*\d+\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _token_overlap(a: str, b: str) -> float:
    """Solapamiento Jaccard sobre tokens. Devuelve 0..1. Mide qué
    fracción del lab name (b) está cubierta por el video title (a)."""
    sa = set(a.split())
    sb = set(b.split())
    if not sb:
        return 0.0
    return len(sa & sb) / len(sb)


def match_video_to_lab(
    video_title: str, labs_index: list[tuple[str, dict]]
) -> dict | None:
    """`labs_index` es [(normalized_name, lab), ...] precomputado.

    Estrategia:
      1. Match estricto: lab name normalized ⊆ video title normalized.
         Si varios matchean, gana el más largo (más específico).
      2. Fallback por solapamiento: si ningún lab cabe entero, pero
         hay alguno con ≥ 70% de tokens cubiertos, gana el de mayor
         solapamiento. Esto cubre cuando Rana trunca títulos largos
         (e.g. "blocked" vs "blocked with absolute path bypass").
    """
    extracted = extract_lab_name_from_title(video_title)
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


def main() -> int:
    if not PORTSWIGGER_LABS_FILE.exists():
        print(
            f"[rana] {PORTSWIGGER_LABS_FILE} no existe. "
            f"Ejecuta antes scripts.fetch_portswigger.",
            file=sys.stderr,
        )
        return 1

    labs = json.loads(PORTSWIGGER_LABS_FILE.read_text(encoding="utf-8"))
    labs_index = [(_normalize(l["name"]), l) for l in labs]

    total_matched = 0
    total_videos = 0
    by_topic_stats: dict[str, dict[str, int]] = {}

    for topic, playlist_id in RANA_SHORT_PLAYLISTS:
        videos = fetch_playlist_videos(playlist_id)
        if not videos:
            print(f"[rana] {topic}: 0 videos", file=sys.stderr)
            continue
        topic_stats = {"videos": len(videos), "matched": 0}
        total_videos += len(videos)

        for v in videos:
            video_url = f"https://youtu.be/{v['id']}"
            lab = match_video_to_lab(v["title"], labs_index)
            if not lab:
                continue
            topic_stats["matched"] += 1
            total_matched += 1
            # Idempotencia: skip si ya existe entrada de Rana con esa URL.
            existing_urls = {w.get("url") for w in lab.get("writeups", [])}
            if video_url in existing_urls:
                continue
            lab.setdefault("writeups", []).append({
                "autor": "Rana Khalil",
                "idioma": "EN",
                "formato": "Vídeo",
                "url": video_url,
            })
        by_topic_stats[topic] = topic_stats

    _yt_cache.save()

    PORTSWIGGER_LABS_FILE.write_text(
        json.dumps(labs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Stats finales
    n_with_rana = sum(
        1 for l in labs
        if any(w.get("autor") == "Rana Khalil" for w in l.get("writeups", []))
    )
    print(
        f"[rana] {total_matched}/{total_videos} videos matched · "
        f"{n_with_rana}/{len(labs)} labs con writeup de Rana Khalil"
    )
    print("[rana] Por playlist:")
    for topic, st in by_topic_stats.items():
        ratio = st["matched"] * 100 // max(st["videos"], 1)
        print(
            f"  {topic:30s} {st['matched']:>3}/{st['videos']:<3} "
            f"({ratio}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
