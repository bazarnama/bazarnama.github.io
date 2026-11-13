#!/usr/bin/env python3
"""Build transparency.html ("شفافیت و اعتبار داده‌ها") from the REAL system files.

Reads api/v1/latest.json, api/v1/source-health.json, data/run-report.json, data/validation-log.json and
data/history-repairs.json. Every number on the page is computed here; nothing is typed by hand. A missing
file or field is shown as "نامشخص" - never guessed. Reuses the style/header/footer of about.html.
Usage: python tools/build_transparency.py
"""
import html, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://bazarnama.github.io"
TITLE = "شفافیت و اعتبار داده‌ها | بازارنما"
DESC = "منابع قیمت، روش اعتبارسنجی، تازگی داده‌ها، وضعیت آخرین اجرا و محدودیت‌های بازارنما، مستقیماً از فایل‌های واقعی سیستم."
UNKNOWN = "نامشخص"
STATUS_FA = {"fresh": "به‌روز", "aging": "در آستانهٔ تأخیر", "stale": "قدیمی", "unknown": UNKNOWN}


def load(rel):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def e(v):
    return html.escape(UNKNOWN if v in (None, "") else str(v))


def age_text(sec):
    if not isinstance(sec, (int, float)) or sec < 0:
        return UNKNOWN
    m = int(sec // 60)
    return f"{m} دقیقه" if m < 120 else f"{m // 60} ساعت"


def build():
    latest = load("api/v1/latest.json") or {}
    health = load("api/v1/source-health.json") or {}
    run = load("data/run-report.json") or {}
    vlog = load("data/validation-log.json") or {}
    repairs = (load("data/history-repairs.json") or {}).get("repairs", [])
    items = latest.get("items", [])
    counts = (latest.get("freshness") or {}).get("counts", {})
    total = len(items)
    two = sum(1 for i in items if i.get("secondary_price") not in (None, ""))
    warn = [i for i in items if i.get("validation_warning") or i.get("discrepancy_warning")]
    held = [i for i in items if (i.get("validation") or {}).get("status") not in (None, "accepted")]
    fresh_ids = {a.get("id"): a for a in (health.get("freshness") or {}).get("assets", [])}

    def kv(label, value):
        return f"<div><small>{html.escape(label)}</small><b>{e(value)}</b></div>"

    cards = "".join([
        kv("دارایی‌های تحت پوشش", total or None),
        kv("به‌روز", counts.get("fresh")),
        kv("در آستانهٔ تأخیر", counts.get("aging")),
        kv("قدیمی", counts.get("stale")),
        kv("با منبع تأییدکنندهٔ دوم", two if total else None),
        kv("تک‌منبعی", (total - two) if total else None),
        kv("دارای هشدار اعتبارسنجی", len(warn) if total else None),
        kv("نگه‌داشته‌شده تا تأیید", len(held) if total else None),
    ])
    rows = []
    for i in sorted(items, key=lambda x: str(x.get("id"))):
        f = i.get("freshness") or fresh_ids.get(i.get("id")) or {}
        name = (i.get("name") or {}).get("fa") or i.get("id")
        disc = i.get("source_discrepancy_pct")
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e(name), e(STATUS_FA.get(f.get("status"), UNKNOWN)), e(age_text(f.get("age_seconds"))),
                e(i.get("source_name")), e(i.get("secondary_source") or "ندارد"),
                e(f"{disc}%" if disc is not None else None), e((i.get("validation") or {}).get("status")),
                "⚠" if (i.get("validation_warning") or i.get("discrepancy_warning")) else "—"))
    table = ("<div class=\"tw\"><table><thead><tr><th>دارایی</th><th>تازگی</th><th>سن داده</th><th>منبع اصلی</th>"
             "<th>منبع دوم</th><th>اختلاف منابع</th><th>اعتبارسنجی</th><th>هشدار</th></tr></thead><tbody>%s</tbody></table></div>"
             % "".join(rows)) if rows else "<p>داده‌ای برای نمایش وجود ندارد.</p>"
    rep = "".join(
        "<li>%s — نقطهٔ %s حذف شد؛ دلیل ثبت‌شده: %s (%s)</li>" % (
            e(r.get("id")), e(r.get("price")), e(r.get("reason")), e(r.get("removed_utc")))
        for r in repairs) or "<li>اصلاحی ثبت نشده است.</li>"
    reasons = "".join("<li><code>%s</code>: %s</li>" % (e(k), e(v)) for k, v in (vlog.get("reasons") or {}).items())
    pol = "".join("<li>%s: %s دقیقه</li>" % (e(k), e(int(v) // 60) if isinstance(v, (int, float)) else e(v))
                  for k, v in ((health.get("freshness") or {}).get("policy") or {}).items())
    body = f"""<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>
<section class="hero"><div class="eyebrow">بازارنما</div><h1>شفافیت و اعتبار داده‌ها</h1><p>این صفحه مستقیماً از فایل‌های واقعی سیستم ساخته می‌شود؛ هر عدد از داده‌های همین سایت محاسبه شده و مقدار ناموجود «{UNKNOWN}» نمایش داده می‌شود.</p></section>
<section class="panel"><h2>وضعیت فعلی</h2><div class="kv">{cards}</div>
<p>آخرین اجرای موفق: <b>{e(run.get("last_success_utc"))}</b> · آخرین خطا: <b>{e(run.get("last_failure_utc") or "ثبت نشده")}</b> · آخرین بررسی تازگی: <b>{e((latest.get("freshness") or {{}}).get("checked_utc"))}</b></p></section>
<section class="panel"><h2>وضعیت هر دارایی</h2>{table}
<p>«منبع دوم» فقط یک مقایسهٔ کمکی است. استقلال کامل منبع اصلی و منبع دوم از یکدیگر تأیید نشده و شباهت قیمت به‌تنهایی دلیل اعتبار نیست.</p></section>
<section class="panel"><h2>روش دریافت و انتخاب منبع</h2><p>قیمت‌ها از یک رابط داده گردآوری‌شده (NerkhAra) دریافت می‌شوند و برای برخی دارایی‌ها با منبع دوم مقایسه می‌شوند؛ رمزارزها و فلزات/نفت هر کدام منبع جداگانهٔ خود را دارند (فهرست در <code>api/v1/source-health.json</code>). بازارنما خودش قیمت‌گذاری نمی‌کند.</p></section>
<section class="panel"><h2>تشخیص داده قدیمی</h2><p>هر دارایی بر اساس زمان اعلام‌شده توسط منبع سنجیده می‌شود، نه زمان دریافت. سقف سن مجاز هر گروه:</p><ul>{pol}</ul><p>داده‌ای که از سقف بگذرد «قدیمی» علامت می‌خورد و نباید قیمت زنده تلقی شود.</p></section>
<section class="panel"><h2>تشخیص جهش غیرعادی</h2><p>قیمت جدید با بازهٔ ۲۴ساعتهٔ تاریخچهٔ خودِ بازارنما و با منبع دوم مقایسه می‌شود. جهش خارج از بازه تا تأیید با دریافت بعدی منتشر نمی‌شود و آخرین قیمت معتبر باقی می‌ماند. نتیجهٔ آخرین اجرا: {e(json.dumps(vlog.get("counts"), ensure_ascii=False) if vlog.get("counts") else None)}.</p><ul>{reasons}</ul></section>
<section class="panel"><h2>اصلاح داده‌های اشتباه</h2><p>اصلاح تاریخچه فقط با ابزار مخصوص انجام می‌شود و هر مورد (دارایی، نقطه، مقدار، دلیل، زمان) در <code>data/history-repairs.json</code> ثبت می‌ماند. این ساختار ممیزی است و ادعای دستکاری‌ناپذیری نیست.</p><ul>{rep}</ul></section>
<section class="panel"><h2>محدودیت‌ها</h2><ul><li>وابستگی به یک رابط داده اصلی؛ قطع آن می‌تواند چند دارایی را همزمان قدیمی کند.</li><li>مجوز بازنشر داده‌های منابع هنوز با تأیید انسانی بررسی نشده است.</li><li>این اطلاعات نرخ رسمی بانکی یا توصیهٔ مالی نیست و ممکن است با قیمت معامله‌شدهٔ واقعی تفاوت داشته باشد.</li><li>تاریخچهٔ قبل از راه‌اندازی بازارنما از منبع داده گرفته شده و به‌طور مستقل بازبینی نشده است.</li></ul></section>
<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/prices.html">همه قیمت‌ها</a> · <a href="/about.html">درباره بازارنما و روش کار</a> · <a href="/transparency.html">شفافیت و اعتبار داده‌ها</a> · <a href="/analysis.html">تحلیل بازار</a></footer>
</main>"""
    src = (ROOT / "about.html").read_text(encoding="utf-8")
    head, rest = src.split("<body>", 1)
    tail = rest[rest.index("<script>(()=>{'use strict'"):]
    url = f"{BASE}/transparency.html"
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": "شفافیت و اعتبار داده‌ها", "url": url,
                     "inLanguage": "fa-IR", "description": DESC}, ensure_ascii=False)
    head = re.sub(r"<title>.*?</title>", lambda m: f"<title>{TITLE}</title>", head, flags=re.S)
    head = re.sub(r"about\.html", "transparency.html", head)
    head = re.sub(r'(name="description" content=")[^"]*', lambda m: m.group(1) + DESC, head)
    head = re.sub(r'(property="og:description" content=")[^"]*', lambda m: m.group(1) + DESC, head)
    head = re.sub(r'(name="twitter:description" content=")[^"]*', lambda m: m.group(1) + DESC, head)
    head = re.sub(r'(og:title" content=")[^"]*', lambda m: m.group(1) + TITLE, head)
    head = re.sub(r'(twitter:title" content=")[^"]*', lambda m: m.group(1) + TITLE, head)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>',
                  lambda m: f'<script type="application/ld+json">{ld}</script>', head, count=1, flags=re.S)
    head = head.replace("</head>", "<style>.tw{overflow-x:auto}.tw table{border-collapse:collapse;width:100%;font-size:14px}"
                        ".tw th,.tw td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right;white-space:nowrap}"
                        "code{direction:ltr;unicode-bidi:embed}</style></head>")
    (ROOT / "transparency.html").write_text(head + "<body><main class=\"wrap\">\n" + body + tail, encoding="utf-8")
    print("transparency.html written:", total, "assets")


if __name__ == "__main__":
    build()
