"""Caché en disco con TTL para no martillear servicios externos
(YouTube, sitemaps, validador) en cada run del pipeline.

Persistencia: un fichero JSON por dominio funcional bajo
`data/_cache/`. Cada entrada lleva timestamp y se descarta si supera
el TTL.

Uso:

    from scripts.cache import JsonCache
    cache = JsonCache("youtube_videos", ttl_days=7)
    if (vid := cache.get(("ippsec", "Lame"))) is not None:
        return vid
    vid = scrape(...)
    cache.set(("ippsec", "Lame"), vid)
    cache.save()
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.config import DATA_DIR


CACHE_DIR = DATA_DIR / "_cache"


def _key_to_str(key: Any) -> str:
    """Acepta tuplas, strings o cualquier objeto serializable."""
    if isinstance(key, str):
        return key
    return json.dumps(key, sort_keys=True, ensure_ascii=False)


class JsonCache:
    def __init__(self, name: str, ttl_days: float):
        self.path = CACHE_DIR / f"{name}.json"
        self.ttl = ttl_days * 86400
        self._data: dict[str, dict] = self._load()
        self._dirty = False

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, key: Any, default: Any = None) -> Any:
        entry = self._data.get(_key_to_str(key))
        if not entry:
            return default
        if time.time() - entry.get("t", 0) > self.ttl:
            return default
        return entry.get("v", default)

    def has(self, key: Any) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def set(self, key: Any, value: Any) -> None:
        self._data[_key_to_str(key)] = {"t": time.time(), "v": value}
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False),
            encoding="utf-8",
        )
        self._dirty = False


# Sentinela para distinguir "no hay clave" de "la clave guarda None"
_MISSING = object()
