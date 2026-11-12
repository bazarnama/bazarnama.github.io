#!/usr/bin/env python3
"""Release gate: validates the generated data and the static SEO files. Exit code 1 = do NOT publish.

  python tools/validate_site.py            # everything (data + site)
  python tools/validate_site.py --data     # only data/*.json and api/ (used right before committing prices/news)
  python tools/validate_site.py --site     # only sitemap, robots, canonicals, internal links
"""
import datetime, json, math, pathlib, re, sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://bazarnama.github.io"
errors, warnings = [], []


def err(msg):
    if msg not in errors:
        errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(f"{path.relative_to(ROOT)}: file is missing")
    except ValueError as e:
        err(f"{path.relative_to(ROOT)}: invalid JSON ({e})")
    return None


def good(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def check_data():
    for p in sorted((ROOT / "data").glob("*.json")) + sorted((ROOT / "api").rglob("*.json")):
        load(p)                                              # every JSON file must parse
    prices = load(ROOT / "data" / "prices.json")
    if isinstance(prices, dict):
        items = prices.get("items")
        if not isinstance(items, list) or not items:
            err("prices.json: items missing or empty")
        else:
            seen = set()
            for i in items:
                pid = i.get("id") if isinstance(i, dict) else None
                if not pid:
                    err("prices.json: item without id")
                    continue
                if pid in seen:
                    err(f"prices.json: duplicate id {pid}")
                seen.add(pid)
                if "price" in i and i["price"] is not None and not good(i["price"]):
                    err(f"prices.json: {pid} has an invalid price {i['price']!r}")
            if len(items) < 20:
                err(f"prices.json: only {len(items)} items (expected a full set)")
    for name in ("history.json", "history-archive.json"):
        doc = load(ROOT / "data" / name)
        series = doc.get("series") if isinstance(doc, dict) else None
        if not isinstance(series, dict) or not series:
            err(f"{name}: series missing")
            continue
        for pid, pts in series.items():
            last = None
            for p in pts:
                if not (isinstance(p, list) and len(p) >= 2 and isinstance(p[0], (int, float)) and good(p[1])):
                    err(f"{name}: {pid} has a malformed point {p!r}")
                    break
                if last is not None and p[0] <= last:
                    err(f"{name}: {pid} timestamps are not strictly increasing near {p[0]}")
                    break
                last = p[0]
    news = load(ROOT / "data" / "news.json")
    if isinstance(news, dict):
        for n in news.get("items", []):
            if not str(n.get("url", "")).startswith("https://") or not n.get("title") or not n.get("source"):
                err(f"news.json: malformed item {str(n)[:80]}")
                break


def check_site():
    try:
        tree = ET.parse(ROOT / "sitemap.xml")
    except (ET.ParseError, FileNotFoundError) as e:
        err(f"sitemap.xml: {e}")
        return
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    today = datetime.datetime.now(datetime.timezone.utc).date()
    locs = []
    for u in tree.getroot().findall("s:url", ns):
        loc = (u.findtext("s:loc", "", ns) or "").strip()
        lastmod = (u.findtext("s:lastmod", "", ns) or "").strip()
        locs.append(loc)
        name = "index.html" if loc == BASE + "/" else loc.replace(BASE + "/", "")
        if not loc.startswith(BASE):
            err(f"sitemap: foreign or malformed loc {loc}")
            continue
        f = ROOT / name
        if not f.exists():
            err(f"sitemap: {loc} has no file")
            continue
        text = f.read_text(encoding="utf-8")
        if re.search(r'name="robots"[^>]*noindex', text):
            err(f"sitemap: {name} is noindex but listed")
        m = re.search(r'<link rel="canonical" href="([^"]*)"', text)
        if not m or m.group(1).rstrip("/") != loc.rstrip("/"):
            err(f"sitemap: {name} canonical {m.group(1) if m else None} != {loc}")
        try:
            if datetime.date.fromisoformat(lastmod) > today:
                err(f"sitemap: {loc} lastmod {lastmod} is in the future")
        except ValueError:
            err(f"sitemap: {loc} lastmod {lastmod!r} is not a date")
    if len(locs) != len(set(locs)):
        err("sitemap: duplicate URLs")
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8") if (ROOT / "robots.txt").exists() else ""
    if f"Sitemap: {BASE}/sitemap.xml" not in robots:
        err("robots.txt: sitemap line missing")
    if re.search(r"^Disallow:\s*/\s*$", robots, re.M):
        err("robots.txt: blocks the whole site")
    pages = {p.name for p in ROOT.glob("*.html")}
    for p in sorted(pages):
        text = (ROOT / p).read_text(encoding="utf-8")
        if p in ("404.html",) or p.startswith("google"):
            continue
        m = re.search(r'<link rel="canonical" href="([^"]*)"', text)
        if not m:
            err(f"{p}: canonical missing")
        elif not m.group(1).startswith(BASE):
            err(f"{p}: canonical points outside the site")
        elif (m.group(1).replace(BASE, "").strip("/") or "index.html") not in pages:
            err(f"{p}: canonical target {m.group(1)} does not exist")
        for link in set(re.findall(r'href="(/[A-Za-z0-9._-]*\.html)(?:[#?][^"]*)?"', text)):
            if link.lstrip("/") not in pages:
                err(f"{p}: broken internal link {link}")
        if not re.search(r"<title>[^<]{5,}</title>", text):
            err(f"{p}: missing or empty <title>")
        if "http-equiv=\"refresh\"" not in text and not re.search(r'<meta name="description" content="[^"]{20,}"', text):
            warn(f"{p}: meta description missing or very short")
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
            try:
                json.loads(block)
            except ValueError as e:
                err(f"{p}: invalid JSON-LD ({e})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"
    if mode in ("--all", "--data"):
        check_data()
    if mode in ("--all", "--site"):
        check_site()
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"validate_site: {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)
