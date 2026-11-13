import json, pathlib, re, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ToolsPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_tools.py")], check=True, capture_output=True)
        cls.text = (ROOT / "tools.html").read_text(encoding="utf-8")

    def test_seo_basics(self):
        self.assertIn('<link rel="canonical" href="https://bazarnama.github.io/tools.html">', self.text)
        self.assertEqual(self.text.count("<title>"), 1)
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.text, re.S)
        self.assertEqual(json.loads(m.group(1))["url"], "https://bazarnama.github.io/tools.html")

    def test_no_innerhtml_and_no_default_fees(self):
        self.assertNotIn("innerHTML", self.text[self.text.index("/*END*/"):])
        self.assertEqual(self.text.count('id="gWage" inputmode="decimal" value="0"'), 1)
        self.assertIn('id="gTax" inputmode="decimal" value="0"', self.text)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_calculations(self):
        s = self.text[self.text.index("/*CALC*/"):self.text.index("/*END*/")]
        js = s + """
const a=gold({weight:'2',karat:18,baseKarat:18,price:1000000,unit:'gram',wagePct:'10',profitPct:'5',taxPct:'10'});
const b=gold({weight:'2',karat:18,baseKarat:24,price:1000000,unit:'gram'});
const m=gold({weight:'1',karat:24,baseKarat:24,price:1,unit:'mesghal'});
const pts=[{timestamp:100*86400,price:10},{timestamp:105*86400,price:12},{timestamp:200*86400,price:20}];
console.log(JSON.stringify({a,b,mg:m.grams,neg:gold({weight:'-1',karat:18,baseKarat:18,price:1,unit:'gram'}),
 bad:gold({weight:'abc',karat:18,baseKarat:18,price:1,unit:'gram'}),pct:gold({weight:'1',karat:18,baseKarat:18,price:1,unit:'gram',taxPct:'150'}),
 num:[num('1,250.5'),num('x'),num('')],p1:onOrBefore(pts,102*86400,7),p2:onOrBefore(pts,150*86400,7),p3:onOrBefore(pts,50*86400,7),
 pl:pnl(2,pts[0],pts[2]),pnone:pnl(2,null,pts[2])}));"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        o = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(o["a"]["raw"], 2000000); self.assertEqual(o["a"]["wage"], 200000)
        self.assertAlmostEqual(o["a"]["profit"], 110000); self.assertAlmostEqual(o["a"]["tax"], 31000)
        self.assertAlmostEqual(o["a"]["total"], 2341000)
        self.assertAlmostEqual(o["b"]["raw"], 1500000)
        self.assertAlmostEqual(o["b"]["total"], 1500000)          # no fees entered -> raw only
        self.assertAlmostEqual(o["mg"], 4.6083)
        self.assertIsNone(o["neg"]); self.assertIsNone(o["bad"]); self.assertIsNone(o["pct"])
        self.assertEqual(o["num"], [1250.5, None, None])
        self.assertEqual(o["p1"]["price"], 10)
        self.assertIsNone(o["p2"]); self.assertIsNone(o["p3"])    # gap > 7 days / before history: no invented price
        self.assertAlmostEqual(o["pl"]["pct"], 100.0); self.assertEqual(o["pl"]["diff"], 20)
        self.assertIsNone(o["pnone"])


if __name__ == "__main__":
    unittest.main()
