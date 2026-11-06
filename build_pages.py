#!/usr/bin/env python3
"""Generate one SEO page per asset (price-<id>.html), about.html and sitemap.xml.
Run:  python scripts/build_pages.py   (output is committed; no build step on the server)
"""
import re, json, html, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://bazarnama.github.io"
GLASS = (ROOT / "glass.css").read_text(encoding="utf-8")
STYLE = re.search(r"<style>(.*?)</style>", (ROOT / "currency.html").read_text(encoding="utf-8"), re.S).group(1)

A = [
 ("usd","دلار آمریکا","قیمت دلار امروز","currency","تومان","دلار آمریکا پرمعامله‌ترین ارز خارجی در بازار ایران است و بسیاری از قیمت‌های دیگر، مثل سکه و طلا، همراه با تغییر آن دنبال می‌شوند."),
 ("eur","یورو","قیمت یورو امروز","currency","تومان","یورو ارز مشترک بسیاری از کشورهای اروپایی است و برای پرداخت‌ها و سفرهای اروپایی بیشتر از دلار مورد توجه قرار می‌گیرد."),
 ("gbp","پوند انگلیس","قیمت پوند امروز","currency","تومان","پوند استرلینگ ارز رسمی بریتانیا است و معمولاً از یورو و دلار گران‌تر معامله می‌شود."),
 ("aed","درهم امارات","قیمت درهم امروز","currency","تومان","درهم امارات به دلیل مراودات تجاری و مسافرتی با امارات، یکی از ارزهای پرتقاضا در بازار ایران است."),
 ("gold-18k","طلای 18 عیار","قیمت طلای 18 عیار امروز","gold","تومان / گرم","طلای 18 عیار رایج‌ترین عیار برای خرید و فروش طلا و زیورآلات است و قیمت آن معمولاً برای هر گرم اعلام می‌شود."),
 ("coin-emami","سکه امامی","قیمت سکه امامی امروز","gold","تومان","سکه امامی پرمعامله‌ترین سکه بازار است. قیمت آن علاوه بر ارزش طلا، به عرضه و تقاضا و حباب بازار هم وابسته است."),
 ("coin-half","نیم‌سکه","قیمت نیم‌سکه امروز","gold","تومان","نیم‌سکه نصف وزن سکه امامی را دارد و برای خریداران با سرمایه کمتر گزینه‌ای رایج است."),
 ("coin-quarter","ربع‌سکه","قیمت ربع‌سکه امروز","gold","تومان","ربع‌سکه کوچک‌ترین سکه رایج بازار است و معمولاً برای هدیه و سرمایه‌گذاری‌های کوچک خریداری می‌شود."),
 ("xau","اونس جهانی طلا","قیمت اونس جهانی طلا امروز","gold","دلار","اونس جهانی طلا مبنای قیمت‌گذاری طلا در بازارهای جهانی است و بر حسب دلار و برای هر اونس تروا اعلام می‌شود."),
 ("btc","بیت‌کوین","قیمت بیت‌کوین امروز","crypto","تتر","بیت‌کوین قدیمی‌ترین و شناخته‌شده‌ترین رمزارز است و قیمت آن در طول روز می‌تواند نوسان زیادی داشته باشد."),
 ("eth","اتریوم","قیمت اتریوم امروز","crypto","تتر","اتریوم دومین رمزارز بزرگ بازار و بستر بسیاری از قراردادهای هوشمند است."),
 ("brent","نفت برنت","قیمت نفت برنت امروز","energy","دلار / بشکه","نفت برنت یکی از دو شاخص اصلی قیمت نفت خام در جهان است و بر حسب دلار برای هر بشکه اعلام می‌شود."),
 ("wti","نفت WTI","قیمت نفت WTI امروز","energy","دلار / بشکه","نفت WTI شاخص قیمت نفت خام آمریکا است و معمولاً با برنت مقایسه می‌شود."),
]
CAT = {"currency":"/currency.html","gold":"/gold.html","crypto":"/crypto.html","energy":"/#markets"}
CATN = {"currency":"قیمت ارز","gold":"طلا و سکه","crypto":"ارز دیجیتال","energy":"نفت"}

HEAD_COMMON = '<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icon-192.png">'
SW = "<script>if('serviceWorker' in navigator)addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}))</script>"
THEME = """const root=document.documentElement,btn=document.getElementById('themeBtn');
function ap(t,s){root.dataset.theme=t;root.style.colorScheme=t;if(btn)btn.textContent=t==='dark'?'☀':'☾';if(s){try{localStorage.setItem('bazarnama-theme',JSON.stringify(t))}catch(e){}}}
let st=null;try{st=JSON.parse(localStorage.getItem('bazarnama-theme'))}catch(e){}
ap(st||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'),false);
if(btn)btn.onclick=()=>ap(root.dataset.theme==='dark'?'light':'dark',true);"""
FOOT = '<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/currency.html">قیمت ارز</a> · <a href="/gold.html">قیمت طلا و سکه</a> · <a href="/crypto.html">قیمت ارز دیجیتال</a> · <a href="/about.html">درباره بازارنما و روش کار</a></footer>'
TOP = '<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>'
EXTRA_CSS = ".kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:14px}.kv div{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:10px 14px}.kv small{display:block;color:var(--muted)}.kv b{font-size:20px}.up{color:#0a8a4a}.down{color:#c0392b}.rel{display:flex;flex-wrap:wrap;gap:8px}.rel a{border:1px solid var(--line);border-radius:999px;padding:3px 13px;text-decoration:none;color:var(--text);background:var(--surface)}"


def page(title, desc, path, body, ld, script=""):
    url = BASE + path
    e = html.escape
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{e(desc)}"><meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{url}"><meta name="theme-color" content="#087e6e">
<meta property="og:type" content="website"><meta property="og:locale" content="fa_IR"><meta property="og:site_name" content="بازارنما"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">
<title>{e(title)}</title>{HEAD_COMMON}
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>{STYLE}{EXTRA_CSS}</style><style id="glass">{GLASS}</style></head><body><main class="wrap">
{TOP}
{body}
{FOOT}
</main><script>(()=>{{'use strict';{THEME}{script}}})();</script>{SW}</body></html>
"""


ASSET_JS = """const ID=%s,UNITS={IRT:'تومان',USD:'دلار',USDT:'تتر'};
const fmt=(v,d)=>new Intl.NumberFormat('fa-IR-u-nu-latn',{maximumFractionDigits:d??(v<10?4:0)}).format(v);
const $=id=>document.getElementById(id);
async function getPrices(){let old=null;try{const r=await fetch('/data/prices.json',{cache:'no-store'});if(r.ok){const d=await r.json();if(d&&Array.isArray(d.items)&&d.items.length){old=d;if(d.fetched_utc&&Date.now()-Date.parse(d.fetched_utc)<20*60*1000)return d;}}}catch(e){}
 try{const c=new AbortController(),t=setTimeout(()=>c.abort(),12000);try{const r=await fetch('https://nerkhara.com/api/v1/latest.json?refresh='+Date.now(),{cache:'no-store',signal:c.signal});if(!r.ok)throw Error();return await r.json();}finally{clearTimeout(t);}}
 catch(e){if(old)return {...old,items:old.items.map(i=>({...i,stale:true}))};throw e;}}
function tl(v){if(!v)return 'نامشخص';const s=String(v),d=new Date(s.endsWith('Z')?s:s+'Z');return isNaN(d)?s:d.toLocaleString('fa-IR-u-nu-latn',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'});}
async function load(){
 try{const data=await getPrices();const x=(data.items||[]).find(i=>i&&i.id===ID);
  if(!x||typeof x.price!=='number'){$('price').textContent='ناموجود';$('status').textContent='قیمتی از منبع دریافت نشد.';return;}
  $('price').textContent=fmt(x.price);$('unit').textContent=UNITS[x.unit]||x.unit||'—';
  if(typeof x.change_pct==='number'){const c=x.change_pct;$('chg').textContent=(c>0?'▲ +':c<0?'▼ ':'• ')+fmt(c,2)+'٪';$('chg').className=c>0?'up':c<0?'down':'';}else $('chg').textContent='نامشخص';
  $('time').textContent=tl(x.updated_utc||x.as_of);$('src').textContent=x.sources?fmt(x.sources)+' منبع':'نامشخص';
  $('status').textContent=x.stale?'اتصال به منبع برقرار نشد؛ آخرین قیمت ذخیره‌شده نمایش داده می‌شود و ممکن است قدیمی باشد.':'قیمت با موفقیت دریافت شد.';
 }catch(e){$('status').textContent='دریافت قیمت ناموفق بود؛ بعداً دوباره تلاش کن.';}}
load();setInterval(load,5*60*1000);"""


def asset_page(a):
    id_, name, h1, cat, unit, blurb = a
    title = f"{h1} | بازارنما"
    desc = f"{h1}؛ نرخ لحظه‌ای {name} به {unit} همراه با درصد تغییر ۲۴ ساعته، زمان آخرین داده و منبع قیمت در بازارنما."
    rel = "".join(f'<a href="/price-{o[0]}.html">{html.escape(o[1])}</a>' for o in A if o[3] == cat and o[0] != id_)
    others = "".join(f'<a href="/price-{o[0]}.html">{html.escape(o[1])}</a>' for o in A if o[3] != cat)
    body = f"""<section class="hero"><div class="eyebrow">بازارنما | {CATN[cat]}</div><h1>{html.escape(h1)}</h1><p>{html.escape(blurb)}</p><div class="actions"><a class="btn" href="/#markets">همه قیمت‌ها</a><a class="btn alt" href="/#alerts">هشدار قیمت</a></div></section>
<section class="panel"><h2>نرخ {html.escape(name)}</h2><div class="kv"><div><small>قیمت</small><b id="price">…</b></div><div><small>واحد</small><b id="unit">{html.escape(unit)}</b></div><div><small>تغییر ۲۴ ساعته</small><b id="chg">…</b></div><div><small>زمان آخرین داده</small><b id="time" style="font-size:15px">…</b></div><div><small>تعداد منابع</small><b id="src" style="font-size:15px">…</b></div></div><p id="status" class="status" aria-live="polite">در حال دریافت اطلاعات…</p></section>
<section class="panel"><h2>نکاتی درباره {html.escape(name)}</h2><p>{html.escape(blurb)}</p><p>قیمت نمایش‌داده‌شده نرخ تقریبی بازار بر پایه داده منبع است و ممکن است با قیمت نهایی معامله در صرافی، بازار یا فروشگاه تفاوت داشته باشد. همیشه واحد قیمت ({html.escape(unit)}) و زمان ثبت داده را کنار عدد بررسی کن. اطلاعات این صفحه توصیه خرید یا فروش نیست.</p><p>برای دیدن نمودار تاریخی و ماشین‌حساب تبدیل، به <a href="/#chart">صفحه اصلی</a> برو. روش جمع‌آوری داده‌ها در <a href="/about.html">درباره بازارنما</a> توضیح داده شده است.</p></section>
<section class="panel"><h2>قیمت‌های مرتبط</h2><div class="rel">{rel}</div><h3>سایر بازارها</h3><div class="rel">{others}</div></section>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title, "url": f"{BASE}/price-{id_}.html", "inLanguage": "fa-IR", "description": desc,
         "isPartOf": {"@type": "WebSite", "name": "بازارنما", "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "بازارنما", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": CATN[cat], "item": BASE + CAT[cat] if CAT[cat].startswith("/") and not CAT[cat].startswith("/#") else BASE + "/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{BASE}/price-{id_}.html"}]}]}
    return page(title, desc, f"/price-{id_}.html", body, ld, ASSET_JS % json.dumps(id_))


def about():
    title = "درباره بازارنما و روش جمع‌آوری قیمت‌ها"
    desc = "بازارنما چیست، قیمت‌ها از کجا می‌آیند، هر چند وقت به‌روز می‌شوند و محدودیت‌های داده‌ها چیست."
    body = """<section class="hero"><div class="eyebrow">بازارنما</div><h1>درباره بازارنما و روش کار</h1><p>بازارنما نمای ساده و سریعی از قیمت ارز، طلا، سکه، رمزارز و نفت است.</p></section>
<section class="panel"><h2>قیمت‌ها از کجا می‌آیند؟</h2><p>قیمت‌ها از رابط داده <a href="https://nerkhara.com/en/api/" rel="noopener noreferrer">NerkhAra</a> گرفته می‌شوند که نرخ را از چند منبع گردآوری می‌کند. بازارنما خودش قیمت‌گذاری نمی‌کند و عدد را تغییر نمی‌دهد؛ فقط نمایش می‌دهد.</p><h2>هر چند وقت به‌روز می‌شود؟</h2><p>یک فرایند خودکار تقریباً هر ۵ دقیقه آخرین قیمت‌ها را ذخیره می‌کند (GitHub Actions اجرای دقیق را تضمین نمی‌کند و ممکن است گاهی دیرتر انجام شود). سایت ابتدا این نسخه ذخیره‌شده را می‌خواند و اگر قدیمی بود، مستقیم از منبع می‌پرسد. اگر منبع در دسترس نباشد، آخرین قیمت ذخیره‌شده با برچسب «قدیمی» نمایش داده می‌شود.</p><h2>زمان داده یعنی چه؟</h2><p>کنار هر قیمت، زمان انتشار داده توسط منبع و تعداد منابع نوشته می‌شود تا بتوانی تازگی عدد را بسنجی.</p><h2>اخبار</h2><p>فقط تیتر، نام منبع، تاریخ و پیوند خبرها از RSS رسانه‌های خبری نمایش داده می‌شود و متن کامل در وب‌سایت ناشر خوانده می‌شود.</p><h2>محدودیت‌ها و سلب مسئولیت</h2><p>قیمت‌ها برای آگاهی عمومی‌اند و تضمین‌کننده قیمت نهایی معامله نیستند. بازار آزاد ممکن است در لحظه با عدد نمایش‌داده‌شده تفاوت داشته باشد. اطلاعات این سایت توصیه سرمایه‌گذاری، خرید یا فروش نیست.</p><h2>هشدار قیمت</h2><p>هشدارهای قیمت در مرورگر خودت ذخیره می‌شوند و فقط وقتی کار می‌کنند که صفحه بازارنما باز باشد؛ اطلاعاتی از تو روی سرور ما نگه داشته نمی‌شود.</p></section>"""
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "name": title, "url": BASE + "/about.html", "inLanguage": "fa-IR", "description": desc}
    return page(title + " | بازارنما", desc, "/about.html", body, ld)


def main():
    for a in A:
        (ROOT / f"price-{a[0]}.html").write_text(asset_page(a), encoding="utf-8")
    (ROOT / "about.html").write_text(about(), encoding="utf-8")
    today = datetime.date.today().isoformat()
    urls = ["/", "/currency.html", "/gold.html", "/crypto.html", "/about.html"] + [f"/price-{a[0]}.html" for a in A]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{BASE}{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n"
    (ROOT / "sitemap.xml").write_text(sm, encoding="utf-8")
    print("built", len(A), "asset pages")


if __name__ == "__main__":
    main()
