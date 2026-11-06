#!/usr/bin/env python3
"""Collect economic headlines from public RSS feeds; store headline, source, date and URL only."""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
FEEDS = [
    ("ایران اینترنشنال", "https://www.iranintl.com/feed"),
    ("ایسنا", "https://www.isna.ir/rss"),
    ("خبرگزاری مهر", "https://www.mehrnews.com/rss"),
    ("تسنیم", "https://www.tasnimnews.com/fa/rss/feed/0/8/0/%D9%85%D9%87%D9%85%D8%AA%D8%B1%DB%8C%D9%86-%D8%A7%D8%AE%D8%A8%D8%A7%D8%B1-%D8%AA%D8%B3%D9%86%DB%8C%D9%85"),
    ("باشگاه خبرنگاران جوان", "https://www.yjc.ir/fa/rss/allnews"),
    ("تابناک", "https://www.tabnak.ir/fa/rss/allnews"),
    ("خبرآنلاین", "https://www.khabaronline.ir/rss"),
]
KEYWORDS = (
    "اقتصاد", "اقتصادی", "بازار", "بورس", "سهام", "ارز", "دلار", "یورو", "طلا", "سکه",
    "تورم", "بانک", "نفت", "گاز", "بنزین", "مسکن", "خودرو", "قیمت", "تجارت", "صادرات",
    "واردات", "یارانه", "حقوق", "دستمزد", "سرمایه", "تولید", "صنعت", "کسب و کار", "معیشت",
    "نرخ بهره", "پتروشیمی", "انرژی", "مالیات", "بودجه", "بازار سرمایه", "رمزارز", "بیت کوین"
)

def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()

def child_text(node, names):
    for child in node.iter():
        if child is node:
            continue
        if local_name(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""

def item_link(node):
    for child in node:
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            value = (child.text or "").strip()
            if href:
                return href
            if value:
                return value
    return ""

def parse_date(value):
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except Exception:
            return ""

def fetch_feed(source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "BazarnamaNewsBot/1.0 (+https://bazarnama.github.io/)"})
    with urllib.request.urlopen(req, timeout=18) as response:
        raw = response.read(3_000_000)
    root = ET.fromstring(raw)
    found = []
    for node in root.iter():
        if local_name(node.tag) not in ("item", "entry"):
            continue
        title = child_text(node, {"title"})
        link = item_link(node)
        date_raw = child_text(node, {"pubdate", "published", "updated", "date"})
        if not title or not link.startswith("http"):
            continue
        if not any(word in title for word in KEYWORDS):
            continue
        found.append({"title": re.sub(r"\s+", " ", title), "url": link, "source": source, "published_at": parse_date(date_raw)})
    return found

def main():
    all_items = []
    successful = 0
    for source, url in FEEDS:
        try:
            all_items.extend(fetch_feed(source, url))
            successful += 1
        except Exception as exc:
            print(f"Feed failed: {source}: {exc}")
    if successful == 0:
        raise SystemExit("All RSS feeds failed; preserving the previous news.json")

    # Newest first; deduplicate near-identical headlines across publishers.
    all_items.sort(key=lambda x: x["published_at"] or "", reverse=True)
    unique, seen = [], set()
    for item in all_items:
        key = re.sub(r"[^\w\u0600-\u06ff]", "", item["title"].lower())[:90]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= 24:
            break

    if not unique:
        raise SystemExit("No economic headlines found; preserving the previous news.json")

    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "items": unique}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    previous = None
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Avoid a commit every 10 minutes when no headlines have changed.
    if previous and previous.get("items") == unique:
        print("No headline changes; keeping existing news.json")
        return
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(unique)} headlines from {successful}/{len(FEEDS)} feeds")

if __name__ == "__main__":
    main()
