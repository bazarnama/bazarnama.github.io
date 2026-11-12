#!/usr/bin/env python3
"""Refresh <lastmod> in sitemap.xml from REAL page changes.

A page's lastmod changes only when the bytes of its HTML file changed since the previous run (SHA-256 kept in
data/page-lastmod.json). Unchanged pages keep their date; nothing is stamped with "today" by default.
First run: the dates already in sitemap.xml are taken as the baseline (their real origin cannot be verified).
Indexable local pages that are missing from the sitemap are added; URLs are never removed.

Usage: python tools/update_sitemap.py [--today YYYY-MM-DD]   (--today exists for tests only)
"""
import datetime, hashlib, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://bazarnama.github.io"
SITEMAP = ROOT / "sitemap.xml"
STATE = ROOT / "data" / "page-lastmod.json"
EXCLUDE = {"404.html"}


def file_for(url):
    path = url[len(BASE):] if url.startswith(BASE) else url
    return "index.html" if path in ("", "/") else path.lstrip("/")


def url_for(name):
    return BASE + "/" if name == "index.html" else f"{BASE}/{name}"


def is_indexable(text, name):
    if name in EXCLUDE or name.startswith("google"):
        return False
    if re.search(r'name="robots"[^>]*noindex', text) or 'http-equiv="refresh"' in text:
        return False
    m = re.search(r'<link rel="canonical" href="([^"]*)"', text)
    return bool(m) and m.group(1).rstrip("/") == url_for(name).rstrip("/")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_sitemap():
    xml = SITEMAP.read_text(encoding="utf-8")
    return [(m.group(1), m.group(2)) for m in re.finditer(r"<url><loc>([^<]+)</loc><lastmod>([^<]*)</lastmod></url>", xml)]


def run(today):
    entries = read_sitemap()
    known = {u for u, _ in entries}
    for f in sorted(ROOT.glob("*.html")):
        if url_for(f.name) not in known and is_indexable(f.read_text(encoding="utf-8"), f.name):
            entries.append((url_for(f.name), today))
            print("added to sitemap:", f.name)
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8")).get("pages", {})
        except ValueError:
            state = {}
    pages, out, changed = {}, [], []
    for url, lastmod in entries:
        name = file_for(url)
        path = ROOT / name
        if not path.exists():
            out.append((url, lastmod))          # never drop or invent anything for a URL without a local file
            continue
        digest = sha(path)
        prev = state.get(name)
        if prev is None:
            new = lastmod                        # baseline: keep the date that is already published
        elif prev.get("sha256") != digest:
            new = today
            changed.append(name)
        else:
            new = prev.get("lastmod", lastmod)
        pages[name] = {"sha256": digest, "lastmod": new}
        out.append((url, new))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in out) + "</urlset>\n"
    SITEMAP.write_text(xml, encoding="utf-8")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"v": 1, "pages": pages}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"sitemap: {len(out)} urls, {len(changed)} changed since last run", changed)
    return changed


if __name__ == "__main__":
    day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    if "--today" in sys.argv:
        day = sys.argv[sys.argv.index("--today") + 1]
    run(day)
