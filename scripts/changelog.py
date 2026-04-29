"""Diffea `data/machines.json` actual contra la versión en HEAD del
repo y produce un resumen tipo:

    +3 máquinas nuevas, +12 writeups, -2 enlaces muertos

Pensado para usarse desde la GitHub Action en el commit message del
cron semanal. También sirve a mano:

    python3 -m scripts.changelog

Si no hay repo git o no hay versión previa de `machines.json`, sale
limpiamente con un mensaje "primera ejecución".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.config import MACHINES_FILE


def _git_show_previous() -> list[dict] | None:
    """Carga `machines.json` desde HEAD vía `git show`. None si no
    existe (primera vez o fichero no trackeado)."""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{MACHINES_FILE.relative_to(Path.cwd())}"],
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


def _summarise(prev: list[dict] | None, curr: list[dict]) -> str:
    if prev is None:
        return f"+{len(curr)} máquinas (primera ejecución)"

    prev_names = {m["name"] for m in prev}
    curr_names = {m["name"] for m in curr}
    added = curr_names - prev_names
    removed = prev_names - curr_names

    def _writeups(machines: list[dict]) -> int:
        return sum(len(m.get("writeups", [])) for m in machines)

    def _skill_links(machines: list[dict]) -> int:
        return sum(len(m.get("skill_links", [])) for m in machines)

    dw = _writeups(curr) - _writeups(prev)
    ds = _skill_links(curr) - _skill_links(prev)

    parts: list[str] = []
    if added:
        parts.append(f"+{len(added)} máquinas")
    if removed:
        parts.append(f"-{len(removed)} máquinas")
    if dw:
        parts.append(f"{dw:+d} writeups")
    if ds:
        parts.append(f"{ds:+d} recursos")
    if not parts:
        return "sin cambios"
    return ", ".join(parts)


def summary() -> str:
    if not MACHINES_FILE.exists():
        return "(sin machines.json)"
    curr = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    prev = _git_show_previous()
    return _summarise(prev, curr)


def main() -> int:
    print(summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
