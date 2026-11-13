import html, json, pathlib, re, subprocess, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def blocks(text):
    return [html.unescape(m) for m in re.findall(r'<pre class="code" dir="ltr">(.*?)</pre>', text, re.S)]


class ApiDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_api_docs.py")], check=True, capture_output=True)
        cls.text = (ROOT / "api-docs.html").read_text(encoding="utf-8")
        cls.latest = json.loads((ROOT / "api/v1/latest.json").read_text(encoding="utf-8"))
        cls.health = json.loads((ROOT / "api/v1/source-health.json").read_text(encoding="utf-8"))

    def test_seo(self):
        self.assertIn('<link rel="canonical" href="https://bazarnama.github.io/api-docs.html">', self.text)
        self.assertEqual(self.text.count("<title>"), 1)
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.text, re.S)
        self.assertEqual(json.loads(m.group(1))["url"], "https://bazarnama.github.io/api-docs.html")

    def test_sample_item_is_real(self):
        item = json.loads(blocks(self.text)[1])
        real = next(i for i in self.latest["items"] if i["id"] == item["id"])
        self.assertEqual(item, real)

    def test_sample_history_is_real_tail(self):
        h = json.loads(blocks(self.text)[2])
        real = json.loads((ROOT / f"api/v1/history/{h['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(h["points"], real["points"][-3:])
        self.assertEqual(h["unit"], real["unit"])

    def test_policy_matches_health_file(self):
        for k, v in self.health["freshness"]["policy"].items():
            self.assertIn(f"<td>{k}</td><td>{int(v) // 60} دقیقه</td>", self.text)

    def test_endpoints_exist_on_disk(self):
        for rel in ("latest.json", "index.json", "source-health.json"):
            self.assertTrue((ROOT / "api/v1" / rel).exists())
            self.assertIn(f"/api/v1/{rel}", self.text)
        self.assertIn("/api/v1/history/{asset_id}.json", self.text)
        self.assertNotIn("None", self.text.split("<main")[1])


if __name__ == "__main__":
    unittest.main()
