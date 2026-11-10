import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://ghimatyar.ir"

def update_schema(filename, transform):
    path = ROOT / filename
    html = path.read_text(encoding="utf-8")

    pattern = re.compile(
        r'(<script[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
        re.I | re.S
    )

    match = pattern.search(html)

    if not match:
        raise ValueError(f"JSON-LD پیدا نشد: {filename}")

    data = json.loads(match.group(2))
    updated = transform(data)

    script = json.dumps(
        updated,
        ensure_ascii=False,
        separators=(",", ":")
    )

    html = (
        html[:match.start()]
        + match.group(1)
        + script
        + match.group(3)
        + html[match.end():]
    )

    path.write_text(html, encoding="utf-8")
    print("اصلاح شد:", filename)


def breadcrumb(label, url):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "قیمت‌یار",
                "item": BASE + "/"
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": label,
                "item": url
            }
        ]
    }


def category_schema(data, label, filename):
    page = {k: v for k, v in data.items() if k != "@context"}

    return {
        "@context": "https://schema.org",
        "@graph": [
            page,
            breadcrumb(label, BASE + "/" + filename)
        ]
    }


def about_schema(data):
    page = {k: v for k, v in data.items() if k != "@context"}

    page["isPartOf"] = {
        "@type": "WebSite",
        "name": "قیمت‌یار",
        "url": BASE + "/"
    }

    return {
        "@context": "https://schema.org",
        "@graph": [
            page,
            breadcrumb("درباره قیمت‌یار", BASE + "/about.html")
        ]
    }


update_schema(
    "currency.html",
    lambda d: category_schema(d, "قیمت ارز", "currency.html")
)

update_schema(
    "gold.html",
    lambda d: category_schema(d, "طلا و سکه", "gold.html")
)

update_schema(
    "crypto.html",
    lambda d: category_schema(d, "ارز دیجیتال", "crypto.html")
)

update_schema("about.html", about_schema)


# بررسی JSON-LD پس از اصلاح
for filename in [
    "currency.html",
    "gold.html",
    "crypto.html",
    "about.html"
]:
    html = (ROOT / filename).read_text(encoding="utf-8")

    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S
    )

    for block in blocks:
        json.loads(block)

print("تمام ساختارهای JSON-LD معتبر هستند.")
