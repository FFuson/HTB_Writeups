"""Fase opcional 4.5: registra cambios entre runs en `data/changelog.json`.

Diffea el `machines.json` actual contra la versión del último commit
(via `git show HEAD:data/machines.json`) y añade una entrada datada
con: máquinas nuevas, máquinas eliminadas, deltas de writeups y
recursos por máquina.

El histórico vive en `data/changelog.json` (tracked) y se renderiza
en `/cambios` desde `generate_mdx.py`.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

from scripts.config import DATA_DIR, MACHINES_FILE


CHANGELOG_FILE = DATA_DIR / "changelog.json"
MAX_ENTRIES = 52  # un año de runs semanales


def _git_show_previous() -> list[dict] | None:
    try:
        rel = MACHINES_FILE.relative_to(Path.cwd())
    except ValueError:
        rel = MACHINES_FILE
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def _writeups_count(m: dict) -> int:
    return len(m.get("writeups", []))


def _resources_count(m: dict) -> int:
    return len(m.get("skill_links", []))


def diff_runs(prev: list[dict] | None, curr: list[dict]) -> dict:
    if prev is None:
        return {
            "first_run": True,
            "added": [m["name"] for m in curr],
            "removed": [],
            "changed": [],
        }

    prev_by_name = {m["name"]: m for m in prev}
    curr_by_name = {m["name"]: m for m in curr}

    added = sorted(set(curr_by_name) - set(prev_by_name))
    removed = sorted(set(prev_by_name) - set(curr_by_name))

    changed: list[dict] = []
    for name in sorted(set(curr_by_name) & set(prev_by_name)):
        a, b = prev_by_name[name], curr_by_name[name]
        d_writeups = _writeups_count(b) - _writeups_count(a)
        d_resources = _resources_count(b) - _resources_count(a)
        if d_writeups or d_resources:
            changed.append(
                {
                    "name": name,
                    "writeups_delta": d_writeups,
                    "resources_delta": d_resources,
                }
            )

    return {
        "first_run": False,
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _load_changelog() -> list[dict]:
    if not CHANGELOG_FILE.exists():
        return []
    try:
        return json.loads(CHANGELOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def main() -> int:
    if not MACHINES_FILE.exists():
        print(f"[changes] {MACHINES_FILE} no existe", file=sys.stderr)
        return 1

    curr = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    prev = _git_show_previous()
    diff = diff_runs(prev, curr)

    if not (diff["added"] or diff["removed"] or diff["changed"]):
        print("[changes] sin cambios — no se registra entrada")
        return 0

    history = _load_changelog()
    today = _dt.date.today().isoformat()
    # Si ya hay entrada de hoy, la sustituimos (idempotencia en mismo día)
    history = [e for e in history if e.get("date") != today]
    history.insert(0, {"date": today, **diff})
    history = history[:MAX_ENTRIES]

    CHANGELOG_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[changes] +{len(diff['added'])} -{len(diff['removed'])} "
        f"~{len(diff['changed'])} máquinas en {today}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
