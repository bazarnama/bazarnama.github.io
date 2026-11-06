import feedparser
import json
import os
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SOURCES = {
    "ایران اینترنشنال": "https://www.iranintl.com/fa/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "تسنیم": "https://www.tasnimnews.com/fa/rss",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    "تابناک": "https://www.tabnak.ir/fa/rss",
}

KEYWORDS = [
    "اقتصاد", "دلار", "ارز", "طلا", "سکه",
    "بورس", "بانک", "تورم", "نفت", "بازار",
    "قیمت", "تجارت", "صادرات", "واردات",
    "رمزارز", "بیت کوین", "بودجه"
]

def get_date(entry):
    try:
        return parsedate_to_datetime(entry.published).astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()

def main():
    news = []
    seen = set()

    for source, url in SOURCES.items():
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "Bazarnama News Bot"}
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            for item in feed.entries[:30]:
                title = item.get("title", "").strip()
                link = item.get("link", "").strip()
                summary = item.get("summary", "")

                text = (title + " " + summary).lower()

                if not title or not link:
                    continue

                if not any(word in text for word in KEYWORDS):
                    continue

                key = title.lower()
                if key in seen:
                    continue

                seen.add(key)

                news.append({
                    "title": title,
                    "source": source,
                    "link": link,
                    "date": get_date(item),
                    "summary": summary[:400]
                })

        except Exception as error:
            print(f"Error in {source}: {error}")

    news.sort(key=lambda x: x["date"], reverse=True)

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as file:
        json.dump(news[:100], file, ensure_ascii=False, indent=2)

    print(f"Saved {len(news[:100])} news items")

if __name__ == "__main__":
    main()
