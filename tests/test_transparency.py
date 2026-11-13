import json, pathlib, re, subprocess, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TransparencyPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_transparency.py")], check=True, capture_output=True)
        cls.text = (ROOT / "transparency.html").read_text(encoding="utf-8")
        cls.latest = json.loads((ROOT / "api/v1/latest.json").read_text(encoding="utf-8"))

    def test_canonical_and_single_title(self):
        self.assertIn('<link rel="canonical" href="https://bazarnama.github.io/transparency.html">', self.text)
        self.assertEqual(self.text.count("<title>"), 1)
        self.assertNotIn("about.html\">", self.text.split("<body>")[0])

    def test_jsonld_valid(self):
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.text, re.S)
        self.assertEqual(json.loads(m.group(1))["url"], "https://bazarnama.github.io/transparency.html")

    def test_every_asset_listed_and_no_placeholders(self):
        for it in self.latest["items"]:
            self.assertIn(it["name"]["fa"], self.text)
        self.assertNotIn("None", self.text)
        self.assertNotIn("nan", self.text.lower().replace("financ", ""))

    def test_counts_match_data(self):
        c = self.latest["freshness"]["counts"]
        self.assertIn(f"<small>به‌روز</small><b>{c['fresh']}</b>", self.text)

    def test_missing_files_show_unknown(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("bt", ROOT / "tools" / "build_transparency.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        self.assertEqual(mod.e(None), "نامشخص")
        self.assertEqual(mod.age_text(-5), "نامشخص")


if __name__ == "__main__":
    unittest.main()
