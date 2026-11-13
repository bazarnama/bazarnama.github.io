"""Regression test: index.html must re-evaluate freshness against the browser clock, so a price file that
was 'fresh' when generated is not shown as live hours later (delayed workflow, old tab, offline cache)."""
import json, pathlib, re, shutil, subprocess, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node not available")
class ClientFreshness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        m = re.search(r"  function reageFreshness\(d\) \{.*?\n    return d;\n  \}\n", html, re.S)
        assert m, "reageFreshness missing from index.html"
        cls.fn = m.group(0)

    def run_js(self, payload, now_iso):
        script = f"{self.fn}\nDate.now=()=>Date.parse({json.dumps(now_iso)});\nconst d={json.dumps(payload)};\nconsole.log(JSON.stringify(reageFreshness(d)));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def item(self, status="fresh", limit=5400):
        return {"id": "usd", "price": 1, "freshness": {"status": status, "observed_utc": "2026-11-13T10:00:00Z",
                                                       "max_age_seconds": limit, "age_seconds": 60}}

    def test_old_file_becomes_stale(self):
        d = self.run_js({"items": [self.item()]}, "2026-11-13T15:00:00Z")
        it = d["items"][0]
        self.assertEqual(it["freshness"]["status"], "stale")
        self.assertTrue(it["stale"])
        self.assertEqual(it["freshness"]["age_seconds"], 18000)

    def test_aging_threshold_matches_server(self):
        d = self.run_js({"items": [self.item()]}, "2026-11-13T11:10:00Z")  # 4200s > 0.65*5400
        self.assertEqual(d["items"][0]["freshness"]["status"], "aging")

    def test_recent_stays_fresh(self):
        d = self.run_js({"items": [self.item()]}, "2026-11-13T10:10:00Z")
        self.assertEqual(d["items"][0]["freshness"]["status"], "fresh")
        self.assertNotIn("stale", d["items"][0])

    def test_unknown_time_untouched(self):
        it = {"id": "x", "freshness": {"status": "unknown", "observed_utc": None, "max_age_seconds": 100}}
        d = self.run_js({"items": [it]}, "2026-11-13T10:10:00Z")
        self.assertEqual(d["items"][0]["freshness"]["status"], "unknown")

    def test_never_downgrades_stale_to_fresh(self):
        d = self.run_js({"items": [self.item(status="stale")]}, "2026-11-13T10:00:30Z")
        self.assertEqual(d["items"][0]["freshness"]["status"], "stale")


if __name__ == "__main__":
    unittest.main()


class AssetPagesReage(unittest.TestCase):
    def test_every_asset_page_reages_and_labels_old_data(self):
        pages = sorted(ROOT.glob("price-*.html"))
        self.assertGreater(len(pages), 30)
        for p in pages:
            t = p.read_text(encoding="utf-8")
            self.assertIn("x.freshness.max_age_seconds*1000", t, p.name)
            self.assertIn("aged?", t, p.name)

    def test_template_and_pages_agree(self):
        self.assertIn("x.freshness.max_age_seconds*1000", (ROOT / "build_pages.py").read_text(encoding="utf-8"))
