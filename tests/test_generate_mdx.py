"""Tests del generador de Mintlify.

Foco en lo que ha roto en producción:
  - `_mdx_safe` debe escapar `<`, `>`, `{`, `}` y `|`.
  - `slugify` debe normalizar acentos y producir slugs idempotentes.
  - `_truncate` corta sin romper estructura de tabla.
"""

from __future__ import annotations

import unittest

from scripts.generate_mdx import _mdx_safe, _truncate, slugify


class MdxSafeTests(unittest.TestCase):
    def test_escapes_jsx_chars(self):
        self.assertEqual(
            _mdx_safe("Samba 3.0.20 < 3.0.25rc3"),
            "Samba 3.0.20 &lt; 3.0.25rc3",
        )
        self.assertEqual(_mdx_safe("a > b"), "a &gt; b")

    def test_escapes_jsx_expressions(self):
        self.assertEqual(
            _mdx_safe("foo {bar} baz"),
            "foo &#123;bar&#125; baz",
        )

    def test_escapes_table_separator(self):
        self.assertEqual(_mdx_safe("a | b"), "a \\| b")

    def test_ampersand_handled(self):
        # & se sustituye antes que el resto, así que el `&lt;` que
        # generamos para `<` no se doble-escapa.
        self.assertEqual(_mdx_safe("a < b & c"), "a &lt; b &amp; c")

    def test_empty_returns_dash(self):
        self.assertEqual(_mdx_safe(""), "—")
        self.assertEqual(_mdx_safe(None), "—")


class SlugifyTests(unittest.TestCase):
    def test_strips_accents(self):
        self.assertEqual(slugify("Fácil"), "facil")
        self.assertEqual(slugify("Ñandú"), "nandu")

    def test_collapses_separators(self):
        self.assertEqual(slugify("Active Directory!"), "active-directory")

    def test_idempotent(self):
        self.assertEqual(slugify(slugify("Buffer Overflow")), "buffer-overflow")

    def test_empty_fallback(self):
        self.assertEqual(slugify(""), "machine")


class TruncateTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(_truncate("hola", 10), "hola")

    def test_truncated_with_ellipsis(self):
        self.assertTrue(_truncate("a" * 100, 20).endswith("…"))
        self.assertEqual(len(_truncate("a" * 100, 20)), 20)

    def test_newlines_collapsed(self):
        # _truncate debe colapsar saltos antes de cortar y luego escapar
        self.assertNotIn("\n", _truncate("foo\nbar\nbaz", 50))


if __name__ == "__main__":
    unittest.main()
