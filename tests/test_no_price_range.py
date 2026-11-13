"""Price ceiling / floor (daily high / low) must not exist anywhere in Bazarnama's data or API."""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import update_prices  # noqa: E402

FORBIDDEN = tuple(update_prices.RANGE_FIELDS)


class StripRangeFieldsTests(unittest.TestCase):
    def test_fields_are_removed_and_other_fields_kept(self):
        items = [{"id": "usd", "price": 100.0, "change_pct": 1.2, "low_24h": 90.0, "high_24h": 110.0},
                 {"id": "btc", "price": 5.0, "low_24h": None}, "not-a-dict", {"id": "eur", "price": 1.0}]
        removed = update_prices.strip_range_fields(items)
        self.assertEqual(removed, 3)
        self.assertEqual(items[0], {"id": "usd", "price": 100.0, "change_pct": 1.2})
        self.assertEqual(items[1], {"id": "btc", "price": 5.0})
        self.assertEqual(items[3], {"id": "eur", "price": 1.0})

    def test_none_and_empty_input_are_safe(self):
        self.assertEqual(update_prices.strip_range_fields(None), 0)
        self.assertEqual(update_prices.strip_range_fields([]), 0)


class PublishedFilesTests(unittest.TestCase):
    def _walk(self, node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                self.assertNotIn(k, FORBIDDEN, f"{path}/{k} must not be published")
                self._walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                self._walk(v, f"{path}[{i}]")

    def test_published_json_has_no_range_fields(self):
        for rel in ("data/prices.json", "api/v1/latest.json", "api/v1/index.json", "data/summary.json"):
            f = ROOT / rel
            if f.exists():
                self._walk(json.loads(f.read_text(encoding="utf-8")), rel)

    def test_no_range_field_names_in_site_sources(self):
        for f in list(ROOT.glob("*.html")) + [ROOT / "build_pages.py", ROOT / "api/v1/README.md"]:
            if f.exists():
                text = f.read_text(encoding="utf-8")
                for name in FORBIDDEN:
                    self.assertNotIn(name, text, f"{f.name} still mentions {name}")


if __name__ == "__main__":
    unittest.main()
