import importlib.util, json, pathlib, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BASE = "https://bazarnama.github.io"
PAGE = ('<!doctype html><html><head><title>صفحه آزمایشی بازارنما</title>'
        '<meta name="description" content="توضیح کوتاه ولی به اندازه کافی طولانی برای آزمون">'
        '<link rel="canonical" href="{canon}"><meta name="robots" content="index,follow"></head><body>{body}</body></html>')


def make_site(tmp, pages):
    tmp = pathlib.Path(tmp)
    (tmp / "data").mkdir()
    for name, body in pages.items():
        url = BASE + "/" if name == "index.html" else f"{BASE}/{name}"
        (tmp / name).write_text(PAGE.format(canon=url, body=body), encoding="utf-8")
    return tmp


def write_sitemap(tmp, entries):
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in entries) + "</urlset>\n"
    (tmp / "sitemap.xml").write_text(xml, encoding="utf-8")


class SitemapLastmodTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = make_site(self.td.name, {"index.html": "home", "a.html": "page a"})
        write_sitemap(self.tmp, [(BASE + "/", "2026-01-01"), (BASE + "/a.html", "2026-01-02")])
        self.m = load("update_sitemap", "tools/update_sitemap.py")
        self.m.ROOT, self.m.SITEMAP, self.m.STATE = self.tmp, self.tmp / "sitemap.xml", self.tmp / "data" / "page-lastmod.json"

    def tearDown(self):
        self.td.cleanup()

    def dates(self):
        return dict(self.m.read_sitemap())

    def test_first_run_keeps_existing_dates(self):
        self.m.run("2026-06-01")
        self.assertEqual(self.dates(), {BASE + "/": "2026-01-01", BASE + "/a.html": "2026-01-02"})

    def test_only_really_changed_page_gets_new_date(self):
        self.m.run("2026-06-01")
        (self.tmp / "a.html").write_text(PAGE.format(canon=BASE + "/a.html", body="changed"), encoding="utf-8")
        changed = self.m.run("2026-06-02")
        self.assertEqual(changed, ["a.html"])
        self.assertEqual(self.dates()[BASE + "/a.html"], "2026-06-02")
        self.assertEqual(self.dates()[BASE + "/"], "2026-01-01")

    def test_rerun_without_change_is_stable(self):
        self.m.run("2026-06-01")
        before = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        self.m.run("2026-09-09")
        self.assertEqual((self.tmp / "sitemap.xml").read_text(encoding="utf-8"), before)

    def test_missing_indexable_page_is_added_but_noindex_is_not(self):
        (self.tmp / "b.html").write_text(PAGE.format(canon=BASE + "/b.html", body="b"), encoding="utf-8")
        (self.tmp / "c.html").write_text(PAGE.format(canon=BASE + "/c.html", body="c").replace("index,follow", "noindex,follow"), encoding="utf-8")
        self.m.run("2026-06-01")
        urls = self.dates()
        self.assertIn(BASE + "/b.html", urls)
        self.assertNotIn(BASE + "/c.html", urls)

    def test_urls_are_never_removed(self):
        write_sitemap(self.tmp, [(BASE + "/", "2026-01-01"), (BASE + "/ghost.html", "2026-01-03")])
        self.m.run("2026-06-01")
        self.assertEqual(self.dates()[BASE + "/ghost.html"], "2026-01-03")


class ValidateSiteTests(unittest.TestCase):
    def fresh(self, pages=None, entries=None):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        pages = pages or {"index.html": "home", "a.html": 'x <a href="/index.html">home</a>'}
        tmp = make_site(self.td.name, pages)
        write_sitemap(tmp, entries or [((BASE + "/" if n == "index.html" else f"{BASE}/{n}"), "2026-01-01") for n in pages])
        (tmp / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
        vs = load("validate_site", "tools/validate_site.py")
        vs.ROOT = tmp
        vs.errors.clear()
        vs.warnings.clear()
        return vs, tmp

    def test_clean_site_passes(self):
        vs, _ = self.fresh()
        vs.check_site()
        self.assertEqual(vs.errors, [])

    def test_future_lastmod_is_an_error(self):
        vs, _ = self.fresh(entries=[(BASE + "/", "2999-01-01"), (BASE + "/a.html", "2026-01-01")])
        vs.check_site()
        self.assertTrue(any("future" in e for e in vs.errors))

    def test_broken_internal_link_and_bad_jsonld(self):
        vs, _ = self.fresh(pages={"index.html": '<a href="/missing.html">x</a><script type="application/ld+json">{bad</script>'})
        vs.check_site()
        self.assertTrue(any("broken internal link" in e for e in vs.errors))
        self.assertTrue(any("JSON-LD" in e for e in vs.errors))

    def test_sitemap_url_without_file_and_xml_errors(self):
        vs, tmp = self.fresh(entries=[(BASE + "/", "2026-01-01"), (BASE + "/gone.html", "2026-01-01")])
        vs.check_site()
        self.assertTrue(any("no file" in e for e in vs.errors))
        (tmp / "sitemap.xml").write_text("<urlset>", encoding="utf-8")
        vs.errors.clear()
        vs.check_site()
        self.assertTrue(any("sitemap.xml" in e for e in vs.errors))

    def test_robots_blocking_everything_is_an_error(self):
        vs, tmp = self.fresh()
        (tmp / "robots.txt").write_text(f"User-agent: *\nDisallow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
        vs.check_site()
        self.assertTrue(any("blocks the whole site" in e for e in vs.errors))

    def test_data_checks(self):
        vs, tmp = self.fresh()
        good = {"items": [{"id": f"x{i}", "price": 1.0} for i in range(25)]}
        (tmp / "data" / "prices.json").write_text(json.dumps(good), encoding="utf-8")
        hist = {"series": {"x0": [[1, 1.0], [2, 2.0]]}}
        for n in ("history.json", "history-archive.json"):
            (tmp / "data" / n).write_text(json.dumps(hist), encoding="utf-8")
        (tmp / "data" / "news.json").write_text(json.dumps({"items": []}), encoding="utf-8")
        vs.check_data()
        self.assertEqual(vs.errors, [])
        hist["series"]["x0"] = [[2, 1.0], [1, 2.0]]
        (tmp / "data" / "history.json").write_text(json.dumps(hist), encoding="utf-8")
        good["items"][0]["price"] = -3
        (tmp / "data" / "prices.json").write_text(json.dumps(good), encoding="utf-8")
        vs.check_data()
        self.assertTrue(any("not strictly increasing" in e for e in vs.errors))
        self.assertTrue(any("invalid price" in e for e in vs.errors))


if __name__ == "__main__":
    unittest.main()
