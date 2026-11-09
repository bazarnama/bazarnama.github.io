
import json
import re
import os
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SOURCES = {
    "ایران اینترنشنال": "https://www.iranintl.com/feed",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/8/0",
    "باشگاه خبرنگاران جوان": "https://www.yjc.ir/fa/rss/allnews",
    "تابناک": "https://www.tabnak.ir/fa/rss/allnews",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    "ایرنا": "https://www.irna.ir/rss"
}

KEYWORDS = [
    "اقتصاد", "اقتصادی", "دلار", "ارز", "طلا", "سکه",
    "بورس", "تورم", "بانک", "نفت", "بازار", "قیمت",
    "تجارت", "صادرات", "واردات", "مسکن", "خودرو",
    "بودجه", "رمزارز", "بیت کوین", "معیشت"
]

def get_date(item):
    for field in ("published", "updated"):
        value = item.get(field)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(
                    timezone.utc
                ).isoformat()
            except Exception:
                pass
    return ""

def main():
    news = []
    seen = set()
    successful = 0

    for source, url in SOURCES.items():
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                print("No entries:", source)
                continue

            successful += 1

            for item in feed.entries[:40]:
                title = item.get("title", "").strip()
                link = item.get("link", "").strip()

                if not title or not link.startswith("https://"):
                    continue

                if not any(word in title for word in KEYWORDS):
                    continue

                key = re.sub(r"\W", "", title.lower())
                if key in seen:
                    continue

                seen.add(key)

                news.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_at": get_date(item)
                })

        except Exception as error:
            print("Error:", source, error)

    if successful == 0:
        raise SystemExit("All news sources failed")

    news.sort(
        key=lambda x: x["published_at"],
        reverse=True
    )

    os.makedirs("data", exist_ok=True)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": news[:24]
    }

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Saved", len(news[:24]), "news items")

if __name__ == "__main__":
    main()
