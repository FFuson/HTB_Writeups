# Cómo contribuir

¡Gracias por considerar contribuir! Este es un proyecto **open
source** y cualquier mejora es bienvenida.

## Tipos de contribución

### Reportar un enlace muerto

Abre un issue con la plantilla `🔗 Enlace muerto` desde
[esta página](https://github.com/FFuson/HTB_Writeups/issues/new/choose).
La plantilla pide: nombre de máquina, autor, URL muerta.

> El pipeline detecta enlaces muertos automáticamente cada lunes
> mediante un `HEAD` request. Reportar manualmente sólo acelera la
> limpieza si hay urgencia.

### Proponer un nuevo autor a la lista blanca

Plantilla `✍️ Nuevo autor en lista blanca`. Antes de proponer,
revisa los criterios:

- Calidad consistente (no posts esporádicos de Medium random).
- Cubre un volumen significativo de máquinas HTB (50+ idealmente).
- Estilo identificable (texto, vídeo o mixto).
- Publica en su propio dominio o en una plataforma estable (no
  blogs personales que mueren cada año).

### Añadir una skill al glosario

Plantilla `🛠 Nueva skill al glosario`. Necesitas:

- Nombre canónico en español + inglés.
- Aliases en cualquier idioma para que el matcher funcione.
- 1-3 URLs a recursos fiables (HackTricks, GTFOBins, PortSwigger,
  Exploit-DB).

El dominio del recurso debe estar en `SKILL_DOMAINS` (en
`scripts/config.py`) o se descartará al validar.

## Setup de desarrollo

```bash
git clone https://github.com/FFuson/HTB_Writeups.git
cd HTB_Writeups
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Para previsualizar el sitio localmente:

```bash
cd docs && npm install --save-dev mint && npx mint dev
```

## Workflow

```bash
# Ejecuta el pipeline completo
python3 -m scripts.pipeline

# Tests
python3 -m unittest discover tests
```

Cada fase se puede lanzar suelta para depurar:

| Script | Qué hace |
|---|---|
| `scripts.fetch_machines` | Obtiene catálogo |
| `scripts.find_writeups` | Descubre URLs de writeups |
| `scripts.find_skills` | Mapea skills al glosario |
| `scripts.validate_links` | HEAD requests + cache |
| `scripts.generate_mdx` | Renderiza MDX + sitemap |

## Pull Requests

1. Fork del repo.
2. Branch desde `main`: `git checkout -b feature/mi-mejora`.
3. Cambios + tests si aplican.
4. Push a tu fork.
5. Abre PR contra `main`. La plantilla del PR pedirá:
   - Tipo de cambio (bug, feature, doc, etc.).
   - Confirmación de tests pasados.
   - Confirmación de no haber subido secretos.

## Estilo de código

- Python 3.10+.
- Sin formatter obligatorio, pero usamos doble comilla y type hints
  modernos (`list[dict]` en lugar de `List[Dict]`).
- Sin docstrings exhaustivos: explica el *por qué*, no el *qué*.
- Cero `print()` decorativo: el log debe servir para depurar
  problemas reales.

## Política de no-romper

- **No inventar URLs.** Si no podemos descubrir un writeup con
  certeza, lo dejamos vacío (mejor que una URL adivinada).
- **No bypass del whitelist.** Cualquier dominio nuevo pasa por
  `WHITELIST_DOMAINS` o `SKILL_DOMAINS`.
- **No clonar contenido.** Sólo enlaces.

## Código de conducta

Sé amable. Estamos aquí porque alguien dedicó horas gratis a
escribir los writeups que enlazamos. Esa generosidad merece
reciprocidad.
