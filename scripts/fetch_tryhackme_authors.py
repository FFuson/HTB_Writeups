"""Matchea videos de YouTube con rooms de TryHackMe para autores curados.

Misma plantilla que `fetch_portswigger_authors.py`. Por ahora dos
autores en lista blanca:

    - JohnHammond — playlist 'TryHackMe' (39 videos), formato
      consistente 'TryHackMe! <room name>'.
    - stuffy24 — playlist 'TryHackMe walkthroughs' (~150 videos),
      títulos variables tipo '<name> TryHackMe Walkthrough!',
      'THM <name>', '<name> THM box walkthrough'.

Estrategia de matching (en orden):
    1. Strip de prefijo/suffix característico del autor.
    2. Substring estricto: room name normalizado ⊆ video title normalizado.
       Si varios matchean, gana el más largo (más específico).
    3. Jaccard ≥ 0.7 sobre tokens (cubre títulos truncados).
    4. Overrides manuales en `data/tryhackme_writeup_overrides.json`
       cuando el matcher no puede inferir sin riesgo.

Salida: actualiza `data/tryhackme_rooms.json` in-place añadiendo
entradas writeup. Idempotente: borra entradas previas del autor antes
de re-añadirlas, así un video renombrado o retirado se actualiza sin
acumular basura.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from scripts.cache import JsonCache
from scripts.config import DATA_DIR

TRYHACKME_ROOMS_FILE = DATA_DIR / "tryhackme_rooms.json"
TRYHACKME_OVERRIDES_FILE = DATA_DIR / "tryhackme_writeup_overrides.json"


AUTHOR_CONFIGS: dict[str, dict] = {
    "JohnHammond": {
        "language": "EN",
        "format": "Vídeo",
        "playlists": [
            ("TryHackMe", "PL1H1sBF1VAKUOm3WyiZ-m2Oqwku4Xp6if"),
        ],
        # 'TryHackMe! <name>' o 'TryHackMe! [<topic>] <name>'
        "strip_prefix_re": re.compile(
            r"^TryHackMe!?\s*(?:\[[^\]]+\]\s*)?[-:]?\s*",
            re.IGNORECASE,
        ),
        "strip_suffix_re": None,
    },
    "stuffy24": {
        "language": "EN",
        "format": "Vídeo",
        "playlists": [
            ("TryHackMe Walkthroughs", "PLrTDbBs5YRrEhmkUXf12qNL_m1MNAcCDM"),
            ("Junior Pentest Path", "PLrTDbBs5YRrFR1ZMcSgm71FiawD4AhWb0"),
            ("Red Team Path", "PLrTDbBs5YRrEKdXgmrnY70N58HYyburr9"),
            ("Cyber Defense", "PLrTDbBs5YRrGDUmyvyjvy_grfh7K3tH4T"),
            ("SOC Level 1", "PLrTDbBs5YRrEnatIZtreJ7oyacRbjmxIk"),
            ("SOC Level 2", "PLrTDbBs5YRrHrla5xqxV30JlP-T1Q7qiT"),
        ],
        # 'THM <name>' / 'THM. <name>' al inicio.
        "strip_prefix_re": re.compile(
            r"^(?:THM[\.\s]+|TryHackMe[\.\s\-:]+)",
            re.IGNORECASE,
        ),
        # Sufijos: 'TryHackMe Walkthrough!', 'THM box walkthrough',
        # 'Walkthrough!', etc.
        "strip_suffix_re": re.compile(
            r"\s*[-—|]?\s*("
            r"TryHackMe Walkthrough!?|"
            r"THM box walkthrough|"
            r"THM Walkthrough|"
            r"Walkthrough[!?]?|"
            r"box walkthrough"
            r")\s*$",
            re.IGNORECASE,
        ),
    },
}


_yt_cache = JsonCache("tryhackme_authors_playlists", ttl_days=30)


def fetch_playlist_videos(playlist_id: str) -> list[dict]:
    cached = _yt_cache.get(playlist_id)
    if cached is not None:
        return cached

    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--flat-playlist", "--dump-single-json",
                "--no-warnings", url,
            ],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[thm-authors] yt-dlp falló para {playlist_id}: {exc}",
              file=sys.stderr)
        return []
    if result.returncode != 0:
        print(f"[thm-authors] yt-dlp rc={result.returncode} para "
              f"{playlist_id}: {result.stderr[:200]}", file=sys.stderr)
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


def _normalize(text: str) -> str:
    """Lowercase + alphanumérico-solo + colapsa whitespace."""
    text = text.lower()
    abbreviations = [
        (r"\bsqli\b", "sql injection"),
        (r"\bxss\b", "cross site scripting"),
        (r"\bssrf\b", "server side request forgery"),
        (r"\bxxe\b", "xml external entity"),
        (r"\bcsrf\b", "cross site request forgery"),
        (r"\&", " and "),
    ]
    for pat, repl in abbreviations:
        text = re.sub(pat, repl, text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_room_name(title: str, cfg: dict) -> str:
    if cfg.get("strip_prefix_re"):
        title = cfg["strip_prefix_re"].sub("", title).strip()
    if cfg.get("strip_suffix_re"):
        title = cfg["strip_suffix_re"].sub("", title).strip()
    return title.strip(" -—|:!?")


def _token_overlap(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())
    if not sb:
        return 0.0
    return len(sa & sb) / len(sb)


def match_video_to_room(
    video_title: str, cfg: dict, rooms_index: list[tuple[str, dict]]
) -> dict | None:
    """rooms_index = [(normalized_name, room), ...]. Devuelve el room
    matcheado o None.

    Los room names de TryHackMe son típicamente cortos (1-3 palabras),
    por eso requerimos longitud mínima en la coincidencia para evitar
    falsos positivos triviales tipo 'Blue' coincidiendo con cualquier
    video que contenga la palabra 'blue'.
    """
    extracted = _extract_room_name(video_title, cfg)
    n_video = _normalize(extracted)
    if not n_video:
        return None

    best_strict: tuple[int, dict] | None = None
    best_overlap: tuple[float, dict] | None = None
    for n_room, room in rooms_index:
        if not n_room:
            continue
        # Para nombres de 1 token (e.g. 'Blue', 'Ice', 'RootMe') exigimos
        # word-boundary match. Para nombres de ≥ 2 tokens, substring
        # estricto sobre normalized. Single-word ≤ 1 char (`a`, `b`)
        # se descarta — demasiado genérico para discriminar.
        if len(n_room) < 2:
            continue
        if " " in n_room:
            # Multi-word: substring directo
            if n_room in n_video:
                score = len(n_room)
                if best_strict is None or score > best_strict[0]:
                    best_strict = (score, room)
        else:
            # Single-word: word-boundary match
            if re.search(rf"\b{re.escape(n_room)}\b", n_video):
                score = len(n_room)
                if best_strict is None or score > best_strict[0]:
                    best_strict = (score, room)

        # Jaccard fallback si el room name tiene ≥ 3 tokens
        if " " in n_room and len(n_room.split()) >= 3:
            ov = _token_overlap(n_video, n_room)
            if ov >= 0.7:
                if best_overlap is None or ov > best_overlap[0]:
                    best_overlap = (ov, room)

    if best_strict is not None:
        return best_strict[1]
    if best_overlap is not None:
        return best_overlap[1]
    return None


def _apply_manual_overrides(rooms: list[dict]) -> int:
    """Aplica overrides manuales si data/tryhackme_writeup_overrides.json
    existe. Idempotente."""
    if not TRYHACKME_OVERRIDES_FILE.exists():
        return 0
    try:
        data = json.loads(TRYHACKME_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[thm-authors] overrides corruptos: {exc}", file=sys.stderr)
        return 0
    overrides = data.get("overrides", [])
    if not overrides:
        return 0
    rooms_by_id = {r["id"]: r for r in rooms}
    applied = 0
    for o in overrides:
        rid = o.get("room_id")
        url = o.get("video_url")
        if not rid or not url:
            continue
        room = rooms_by_id.get(rid)
        if room is None:
            print(f"[thm-authors] override: room_id {rid!r} no existe — "
                  f"skip {url}", file=sys.stderr)
            continue
        existing_urls = {w.get("url") for w in room.get("writeups", [])}
        if url in existing_urls:
            continue
        room.setdefault("writeups", []).append({
            "autor": o.get("author", "Unknown"),
            "idioma": o.get("language", "EN"),
            "formato": o.get("format", "Vídeo"),
            "url": url,
        })
        applied += 1
    return applied


def main() -> int:
    if not TRYHACKME_ROOMS_FILE.exists():
        print(f"[thm-authors] {TRYHACKME_ROOMS_FILE} no existe. "
              f"Ejecuta antes scripts.fetch_tryhackme.",
              file=sys.stderr)
        return 1

    rooms = json.loads(TRYHACKME_ROOMS_FILE.read_text(encoding="utf-8"))
    rooms_index = [(_normalize(r["name"]), r) for r in rooms]

    grand_videos = 0
    grand_matched = 0

    for author, cfg in AUTHOR_CONFIGS.items():
        # Limpieza idempotente
        for r in rooms:
            r["writeups"] = [
                w for w in r.get("writeups", [])
                if w.get("autor") != author
            ]

        author_videos = 0
        author_matched = 0
        per_playlist_stats: dict[str, dict] = {}

        for playlist_label, playlist_id in cfg["playlists"]:
            videos = fetch_playlist_videos(playlist_id)
            stats = {"videos": len(videos), "matched": 0}
            author_videos += len(videos)

            for v in videos:
                video_url = f"https://youtu.be/{v['id']}"
                room = match_video_to_room(v["title"], cfg, rooms_index)
                if not room:
                    continue
                stats["matched"] += 1
                author_matched += 1
                existing_urls = {
                    w.get("url") for w in room.get("writeups", [])
                }
                if video_url in existing_urls:
                    continue
                room.setdefault("writeups", []).append({
                    "autor": author,
                    "idioma": cfg["language"],
                    "formato": cfg["format"],
                    "url": video_url,
                })
            per_playlist_stats[playlist_label] = stats

        n_with_author = sum(
            1 for r in rooms
            if any(w.get("autor") == author for w in r.get("writeups", []))
        )
        print(f"[thm-authors] {author}: {author_matched}/{author_videos} "
              f"videos matched · {n_with_author}/{len(rooms)} rooms cubiertas")
        for label, st in per_playlist_stats.items():
            ratio = st["matched"] * 100 // max(st["videos"], 1)
            print(f"  {label:30s} {st['matched']:>3}/{st['videos']:<3} "
                  f"({ratio}%)")
        grand_videos += author_videos
        grand_matched += author_matched

    overrides_applied = _apply_manual_overrides(rooms)
    if overrides_applied:
        print(f"[thm-authors] overrides manuales: {overrides_applied} "
              f"entradas aplicadas")

    _yt_cache.save()

    TRYHACKME_ROOMS_FILE.write_text(
        json.dumps(rooms, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_with_any_extra = sum(
        1 for r in rooms
        if any(
            w.get("autor") in AUTHOR_CONFIGS
            for w in r.get("writeups", [])
        )
    )
    print(f"[thm-authors] TOTAL: {grand_matched + overrides_applied} "
          f"videos matched · {n_with_any_extra}/{len(rooms)} rooms con "
          f"writeup de algún autor whitelist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
