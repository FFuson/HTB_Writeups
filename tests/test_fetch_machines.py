"""Tests del parser JS de htbmachines.

Cubrimos los casos que históricamente nos rompieron:
  - URLs con `https://` no deben confundirse con keys.
  - Comentarios `//` dentro de strings deben sobrevivir.
  - Llamadas a función JS (`count()`, `crypto.randomUUID()`) deben sustituirse.
  - Llaves balanceadas en strings.
"""

from __future__ import annotations

import json
import unittest

from scripts.fetch_machines import (
    _extract_balanced,
    _extract_dataset_objects,
    _js_object_to_json,
)


class JsObjectToJsonTests(unittest.TestCase):
    def test_url_not_split_by_colon_in_string(self):
        obj = '{ name: "Lame", youtube: "https://www.youtube.com/watch?v=abc" }'
        result = json.loads(_js_object_to_json(obj))
        self.assertEqual(result["youtube"], "https://www.youtube.com/watch?v=abc")
        self.assertEqual(result["name"], "Lame")

    def test_function_calls_replaced(self):
        obj = '{ id: count(), sku: crypto.randomUUID(), name: "X" }'
        result = json.loads(_js_object_to_json(obj))
        self.assertIsNone(result["id"])
        self.assertEqual(result["sku"], "")
        self.assertEqual(result["name"], "X")

    def test_line_comment_inside_string_preserved(self):
        obj = '{ url: "https://example.com/path", x: 1 }'
        result = json.loads(_js_object_to_json(obj))
        # `//` dentro del string no debe truncarse
        self.assertEqual(result["url"], "https://example.com/path")

    def test_trailing_comma_handled(self):
        obj = '{ name: "X", value: 1, }'
        result = json.loads(_js_object_to_json(obj))
        self.assertEqual(result["value"], 1)


class ExtractBalancedTests(unittest.TestCase):
    def test_string_with_brace_inside(self):
        src = 'before { skills: "Buffer { overflow }", x: 1 } after'
        body, end = _extract_balanced(src, src.index("{"))
        self.assertTrue(body.startswith("{"))
        self.assertTrue(body.endswith("}"))
        # No debe haber roto en la `}` del string interno
        self.assertIn('"Buffer { overflow }"', body)


class ExtractDatasetObjectsTests(unittest.TestCase):
    def test_array_literal_and_pushes(self):
        src = """
        const Dataset = [
          { name: "A" },
          { name: "B" },
        ];
        Dataset.push({ name: "C" });
        Dataset.push(  { name: "D" }  );
        """
        objs = _extract_dataset_objects(src)
        self.assertEqual(len(objs), 4)
        names = [json.loads(_js_object_to_json(o))["name"] for o in objs]
        self.assertEqual(sorted(names), ["A", "B", "C", "D"])


if __name__ == "__main__":
    unittest.main()
