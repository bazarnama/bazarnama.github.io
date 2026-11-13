import json, pathlib, re, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AnalysisPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_analysis.py")], check=True, capture_output=True)
        cls.text = (ROOT / "analysis.html").read_text(encoding="utf-8")

    def test_seo_basics(self):
        self.assertIn('<link rel="canonical" href="https://bazarnama.github.io/analysis.html">', self.text)
        self.assertEqual(self.text.count("<title>"), 1)
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.text, re.S)
        self.assertEqual(json.loads(m.group(1))["url"], "https://bazarnama.github.io/analysis.html")

    def test_no_unsafe_html_injection(self):
        script = self.text[self.text.index("/*END*/"):]
        self.assertNotIn("innerHTML", script)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_stats_math(self):
        s = self.text[self.text.index("/*STATS*/"):self.text.index("/*END*/")]
        js = s + """
const P=a=>a.map((p,i)=>({timestamp:i*86400,price:p}));
const r=stats(P([100,110,99,120]));
const g=stats([{timestamp:0,price:1},{timestamp:9*86400,price:2}]);
console.log(JSON.stringify({r,g,one:stats(P([5])),w:windowPts(P([1,2,3,4]),2).length,empty:windowPts([],5).length}));"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        out = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout)
        self.assertAlmostEqual(out["r"]["change"], 20.0, places=6)
        self.assertAlmostEqual(out["r"]["maxDrop"], -10.0, places=6)
        self.assertAlmostEqual(out["r"]["maxRise"], 21.2121, places=3)
        self.assertEqual(out["g"]["gaps"], 1)
        self.assertIsNone(out["one"])          # not enough data -> no numbers
        self.assertEqual(out["w"], 3)
        self.assertEqual(out["empty"], 0)


if __name__ == "__main__":
    unittest.main()
