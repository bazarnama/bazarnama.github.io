#!/usr/bin/env python3
"""Collect economic headlines from the RSS feeds of Iranian news outlets and write data/news.json.

Only title, outlet name, link and the publisher's own date are stored (no generated summaries or quotes).
Relevance, category, de-duplication and date rules live in news_quality.py.
If every source fails, or nothing passes the quality rules, the previous data/news.json is left untouched.
"""
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import news_quality  # noqa: E402

SOURCES = {
    "ایران اینترنشنال": "https://www.iranintl.com/feed",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/8/0",
    "باشگاه خبرنگاران جوان": "https://www.yjc.ir/fa/rss/allnews",
    "تابناک": "https://www.tabnak.ir/fa/rss/allnews",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
}
OUT = ROOT / "data" / "news.json"
PER_SOURCE = 40


def entry_date(item):
    """Publisher date of an RSS entry: the raw text first, the parsed struct as a fallback."""
    for field in ("published", "updated"):
        if item.get(field):
            return item.get(field)
    for field in ("published_parsed", "updated_parsed"):
        if item.get(field):
            return tuple(item.get(field))[:6]      # feedparser gives UTC struct_time
    return None


def collect():
    import feedparser  # imported here so the pure logic can be tested without it
    raw, ok_sources, failed = [], [], []
    for source, url in SOURCES.items():
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print("No entries:", source)
                failed.append(source)
                continue
            ok_sources.append(source)
            for item in feed.entries[:PER_SOURCE]:
                raw.append({"title": item.get("title", ""), "url": item.get("link", ""), "source": source,
                            "date": entry_date(item)})
        except Exception as error:  # noqa: BLE001
            print("Error:", source, error)
            failed.append(source)
    return raw, ok_sources, failed


def main():
    raw, ok_sources, failed = collect()
    if not ok_sources:
        raise SystemExit("All news sources failed; keeping the previous data/news.json")
    items, stats = news_quality.build_items(raw, datetime.now(timezone.utc))
    print("News stats:", stats)
    if not items:
        raise SystemExit("No headline passed the quality rules; keeping the previous data/news.json")
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "stats": stats,
        "sources_ok": ok_sources,
        "sources_failed": failed,
    }
    os.makedirs(OUT.parent, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT)
    print("Saved", len(items), "news items")


if __name__ == "__main__":
    main()
