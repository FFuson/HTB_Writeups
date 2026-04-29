"""Orquestador: ejecuta las cuatro fases en orden y aborta si alguna
falla. Pensado para correrse a mano (`python -m scripts.pipeline`) o
desde un cron / GitHub Action.

Forzamos `sys.stdout/sys.stderr` con line-buffering para que los logs
de las cuatro fases se entrelacen en orden cronológico real cuando la
salida va a `tee` o a un fichero.
"""

from __future__ import annotations

import sys
import time

# Activar line-buffering antes de importar cualquier subfase.
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from scripts import (  # noqa: E402
    fetch_machines,
    find_skills,
    find_writeups,
    generate_mdx,
    validate_links,
)


PHASES = [
    ("fetch_machines", fetch_machines.main),
    ("find_writeups", find_writeups.main),
    ("find_skills", find_skills.main),
    ("validate_links", validate_links.main),
    ("generate_mdx", generate_mdx.main),
]


def main() -> int:
    start_total = time.monotonic()
    for name, runner in PHASES:
        print("\n" + "=" * 60, flush=True)
        print(f"  Fase: {name}", flush=True)
        print("=" * 60, flush=True)
        start = time.monotonic()
        rc = runner()
        elapsed = time.monotonic() - start
        print(f"[{name}] rc={rc} · {elapsed:.1f}s", flush=True)
        if rc != 0:
            print(
                f"\n[pipeline] {name} falló (rc={rc}), abortando",
                file=sys.stderr,
                flush=True,
            )
            return rc

    total = time.monotonic() - start_total
    print(f"\n[pipeline] OK · total {total:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
