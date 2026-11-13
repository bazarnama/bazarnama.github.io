#!/usr/bin/env python3
"""Build api-docs.html ("مستندات API بازارنما") from REAL API files.

Sample responses are copied from api/v1/*.json (never typed by hand); freshness thresholds come from
api/v1/source-health.json; validation reasons from data/validation-log.json. Fields whose exact meaning is
defined by the upstream provider are labelled as such instead of being guessed. Usage: python tools/build_api_docs.py
"""
import collections, html, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shell import shell, ROOT

TITLE = "مستندات API بازارنما (نسخهٔ ۱): قیمت، تاریخچه و سلامت منابع | بازارنما"
DESC = "راهنمای API عمومی و بدون کلید بازارنما با نمونهٔ واقعی درخواست و پاسخ، واحدها، وضعیت تازگی، اعتبارسنجی و سیاست پایداری نسخه."
CSS = """pre.code{direction:ltr;text-align:left;overflow-x:auto;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:10px 14px;font-size:13px;line-height:1.6;unicode-bidi:plaintext}.tw{overflow-x:auto}.tw table{border-collapse:collapse;width:100%;font-size:14px}.tw th,.tw td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right}.tw td:first-child{direction:ltr;text-align:left;white-space:nowrap}code{direction:ltr;unicode-bidi:embed}"""


def load(rel):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pre(obj):
    return '<pre class="code" dir="ltr">%s</pre>' % html.escape(json.dumps(obj, ensure_ascii=False, indent=2))


def table(rows, head):
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    tr = "".join("<tr>%s</tr>" % "".join(f"<td>{c}</td>" for c in r) for r in rows)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


FIELDS = [
    ("id", "شناسهٔ دارایی؛ همان نام فایل تاریخچه."), ("family", "گروه: currency، gold، coin، metal، crypto، energy."),
    ("name.fa / name.en", "نام دارایی."), ("unit", "واحد قیمت، مثلاً IRT (تومان)، USD، USDT. قیمت‌ها را بدون توجه به این فیلد با هم جمع یا مقایسه نکنید."),
    ("price", "قیمت فعلی در واحد <code>unit</code>."), ("change_pct", "درصد تغییر ۲۴ساعته؛ ممکن است <code>null</code> باشد."),
    ("stale", "اگر <code>true</code> باشد قیمت زنده تلقی نشود."), ("updated_utc", "زمان به‌روزرسانی ثبت‌شده توسط منبع."),
    ("freshness.status", "وضعیت تازگی: fresh، aging، stale، unknown."), ("freshness.observed_utc", "زمان اعلام قیمت توسط منبع."),
    ("freshness.checked_utc", "زمان بررسی توسط بازارنما."), ("freshness.age_seconds / max_age_seconds", "سن داده و سقف مجاز آن گروه."),
    ("freshness.clock_basis", "مبنای ساعت: <code>provider_timestamp</code> یعنی ساعت خود منبع؛ <code>unknown</code> یعنی زمان معتبر موجود نبود."),
    ("source_name / secondary_source", "منبع اصلی و (در صورت وجود) منبع مقایسه‌کننده."),
    ("source_discrepancy_pct", "اختلاف درصدی با منبع دوم؛ فقط وقتی منبع دوم دارد."),
    ("validation.status / validation.reason", "نتیجهٔ اعتبارسنجی بازارنما (جدول دلایل پایین‌تر)."),
    ("validation_warning / discrepancy_warning", "هشدار اعتبارسنجی یا اختلاف بیش از آستانه."),
    ("sources, method, spread_pct, as_of, price_irt", "ارائه‌شده توسط منبع داده؛ معنی دقیق به مستندات آن منبع بستگی دارد و بازارنما آن‌ها را بازتعریف نمی‌کند. ممکن است نباشند."),
    ("page, history (داخل هر قلم)", "<b>توجه:</b> این آدرس‌ها به وب‌سایت منبع داده اشاره می‌کنند، نه بازارنما. تاریخچهٔ بازارنما فقط از الگوی <code>history_pattern</code> در <code>index.json</code> خوانده شود."),
]


def build():
    latest = load("api/v1/latest.json") or {}
    index = load("api/v1/index.json") or {}
    health = load("api/v1/source-health.json") or {}
    vlog = load("data/validation-log.json") or {}
    items = latest.get("items", [])
    sample_item = next((i for i in items if i.get("id") == "usd"), items[0] if items else None)
    hist = load(f"api/v1/history/{sample_item['id']}.json") if sample_item else None
    hs = dict(hist) if hist else None
    if hs:
        hs["points"] = hs["points"][-3:]
    top = {k: latest[k] for k in ("api", "generated_utc", "fetched_utc", "freshness") if k in latest}
    top["items"] = ["... %d items ..." % len(items)]
    sh = {"schema": health.get("schema"), "freshness": {"policy": (health.get("freshness") or {}).get("policy"),
                                                       "counts": (health.get("freshness") or {}).get("counts")}}
    pol = (health.get("freshness") or {}).get("policy") or {}
    pol_rows = [(html.escape(k), "%s دقیقه" % (int(v) // 60)) for k, v in pol.items()]
    reason_rows = [("<code>%s</code>" % html.escape(k), html.escape(str(v))) for k, v in (vlog.get("reasons") or {}).items()]
    fam = collections.Counter(i.get("family") for i in items)
    base = "https://bazarnama.github.io"
    aid = (sample_item or {}).get("id", "usd")
    body = f"""<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>
<section class="hero"><div class="eyebrow">بازارنما</div><h1>مستندات API نسخهٔ ۱</h1><p>API عمومی، ایستا و بدون کلید. نمونه‌های این صفحه از فایل‌های واقعی API ساخته شده‌اند.</p></section>
<section class="panel"><h2>نقاط دسترسی</h2>{table([
 ("<code>GET /api/v1/latest.json</code>", "آخرین قیمت‌ها (%d قلم؛ %s)" % (len(items), "، ".join(f"{k}: {v}" for k, v in sorted(fam.items())))),
 ("<code>GET /api/v1/history/{asset_id}.json</code>", "تاریخچهٔ قیمت؛ فهرست شناسه‌ها در <code>index.json</code> (%d دارایی)" % len(index.get("history_assets", []))),
 ("<code>GET /api/v1/index.json</code>", "فهرست دارایی‌ها و الگوی مسیر تاریخچه"),
 ("<code>GET /api/v1/source-health.json</code>", "سلامت منابع، سقف تازگی و تعداد هر وضعیت")], ["مسیر", "توضیح"])}
<p>پایهٔ آدرس: <code>{base}</code>. فایل‌ها ایستا هستند و با GitHub Actions بازسازی می‌شوند؛ زمان واقعی به‌روزرسانی را از <code>freshness</code> بخوانید، نه از زمان درخواست.</p></section>
<section class="panel"><h2>نمونه: latest.json (ساختار)</h2>{pre(top)}<h3>یک قلم واقعی</h3>{pre(sample_item)}</section>
<section class="panel"><h2>فیلدها</h2>{table(FIELDS, ["فیلد", "معنی"])}</section>
<section class="panel"><h2>نمونه: تاریخچه ({html.escape(aid)}، سه نقطهٔ آخر)</h2>{pre(hs)}<p><code>timestamp</code> یعنی Unix UTC بر حسب ثانیه و <code>price</code> در همان <code>unit</code> سطح بالای فایل است. فاصلهٔ نقاط یکنواخت نیست (سال‌های قدیم معمولاً روزانه‌اند و نقاط اخیر می‌توانند ساعتی باشند) و ممکن است شکاف داشته باشد؛ نقطهٔ گمشده را درون‌یابی نکنید.</p></section>
<section class="panel"><h2>تازگی و سقف سن</h2>{table(pol_rows, ["گروه", "حداکثر سن"])}<p>وضعیت <code>aging</code> از ۶۵٪ سقف شروع می‌شود. سری‌های روزانه (مثل برنت و WTI فیزیکی، سبد اوپک، گاز طبیعی) آستانه‌های بلندتری دارند؛ جزئیات در <code>DATA-FRESHNESS.md</code>. نمونهٔ <code>source-health.json</code>:</p>{pre(sh)}</section>
<section class="panel"><h2>اعتبارسنجی</h2><p>دلایل ممکن برای <code>validation.reason</code> (از آخرین اجرا):</p>{table(reason_rows, ["دلیل", "معنی"])}</section>
<section class="panel"><h2>نمونهٔ اجرا</h2><pre class="code" dir="ltr">{html.escape(f'''# curl
curl -s {base}/api/v1/latest.json | jq '.items[] | select(.id=="{aid}") | {{price, unit, freshness: .freshness.status}}'

# JavaScript
const r = await fetch("{base}/api/v1/latest.json");
const {{ items }} = await r.json();
const x = items.find(i => i.id === "{aid}");
if (x.stale || x.freshness.status !== "fresh") console.warn("not live");

# Python
import requests
d = requests.get("{base}/api/v1/history/{aid}.json", timeout=15).json()
print(d["unit"], d["points"][-1])''')}</pre></section>
<section class="panel"><h2>سیاست پایداری</h2><ul><li>مسیرها و نام فیلدهای v1 حذف یا تغییر نمی‌کنند؛ فقط فیلد اضافه می‌شود. کد شما باید فیلدهای ناشناخته را نادیده بگیرد.</li><li>تغییر ناسازگار فقط در مسیر <code>/api/v2/</code> منتشر می‌شود.</li><li>بدون کلید و بدون محدودیت رسمی؛ بیش از یک خواندن در دقیقه برای هر فایل لازم نیست. بدون SLA.</li><li>داده «لحظه‌ای» تضمین‌شده نیست؛ فقط <code>freshness.status = fresh</code> به‌معنی تازه بودن طبق سیاست بالاست و قیمت <code>stale</code> نباید زنده تلقی شود.</li><li>مجوز بازنشر داده‌های منبع هنوز با تأیید انسانی بررسی نشده؛ پیش از استفادهٔ تجاری آن را بررسی کنید.</li></ul></section>
<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/prices.html">همه قیمت‌ها</a> · <a href="/transparency.html">شفافیت و اعتبار داده‌ها</a> · <a href="/tools.html">ابزارهای بازارنما</a> · <a href="/api-docs.html">مستندات API</a> · <a href="/about.html">درباره بازارنما و روش کار</a></footer>
</main>"""
    shell("api-docs.html", TITLE, DESC, "TechArticle", "مستندات API بازارنما", body, CSS)
    print("api-docs.html written")


if __name__ == "__main__":
    build()
