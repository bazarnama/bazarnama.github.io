#!/usr/bin/env python3
"""Build analysis.html ("تحلیل بازار"): multi-asset comparison, heat map, historical stats.

All numbers are computed in the browser from /api/v1/latest.json and /api/v1/history/{id}.json. Nothing is
invented: a window with fewer than 2 real points shows "داده کافی نیست". Reuses the shell of about.html.
Usage: python tools/build_analysis.py
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://bazarnama.github.io"
TITLE = "تحلیل بازار: مقایسه دارایی‌ها و نوسانات | بازارنما"
DESC = "مقایسهٔ شاخص‌شدهٔ چند دارایی، نقشهٔ حرارتی تغییرات و آمار نوسان تاریخی بر پایهٔ تاریخچهٔ واقعی بازارنما؛ توصیف گذشته است، نه پیش‌بینی."

CSS = """.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.chips button{font:inherit;border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:999px;padding:3px 13px;cursor:pointer}.chips button[aria-pressed=true]{background:var(--brand);color:#fff;border-color:var(--brand)}
.heat{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}.heat a{display:block;text-decoration:none;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:8px 10px;background:var(--bg);line-height:1.5}.heat a.up{background:color-mix(in srgb,#0a8a4a 18%,var(--surface))}.heat a.down{background:color-mix(in srgb,#c0392b 18%,var(--surface))}.heat a.old{opacity:.55;border-style:dashed}.heat small{display:block;color:var(--muted)}
.tw{overflow-x:auto}.tw table{border-collapse:collapse;width:100%;font-size:14px}.tw th,.tw td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right;white-space:nowrap}
#chart{width:100%;height:auto;display:block}#chart text{fill:var(--muted);font-size:11px}.msg{color:var(--muted)}"""

BODY = """<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>
<section class="hero"><div class="eyebrow">بازارنما</div><h1>تحلیل بازار</h1><p>مقایسه و آمار توصیفی بر پایهٔ تاریخچهٔ واقعی ثبت‌شده. این صفحه پیش‌بینی یا توصیهٔ سرمایه‌گذاری نیست.</p></section>
<section class="panel"><h2>نقشهٔ حرارتی تغییرات</h2><p class="msg" id="heatNote">در حال بارگذاری…</p><div class="heat" id="heat"></div><p class="msg">درصد تغییر همان مقدار ثبت‌شده در API است. کاشی کم‌رنگ و خط‌چین یعنی داده به‌روز نیست؛ «نامشخص» یعنی منبع درصد تغییر نداده است.</p></section>
<section class="panel"><h2>مقایسهٔ چند دارایی</h2><p>دارایی‌ها را انتخاب کنید (تا ۶ مورد). چون واحد قیمت‌ها متفاوت است، همه از ۱۰۰ در ابتدای بازه شروع می‌شوند و فقط درصد تغییر نسبی مقایسه می‌شود.</p>
<div class="chips" id="assets" role="group" aria-label="انتخاب دارایی"></div>
<div class="chips" id="ranges" role="group" aria-label="بازه زمانی"></div>
<p class="msg" id="status" role="status"></p>
<svg id="chart" viewBox="0 0 640 280" role="img" aria-label="نمودار مقایسه‌ای شاخص‌شده"></svg>
<div class="tw"><table id="stats"></table></div>
<p class="msg" id="notes"></p></section>
<section class="panel"><h2>روش محاسبه</h2><ul><li>شاخص = قیمت ÷ قیمت اولین نقطهٔ واقعی بازه × ۱۰۰. نقاط گمشده درون‌یابی نمی‌شوند؛ خط فقط نقاط واقعی را وصل می‌کند.</li><li>نوسان = انحراف معیار تغییرات درصدی بین نقاط متوالی (روزانه).</li><li>بیشترین افت = بزرگ‌ترین کاهش از یک قلهٔ قبلی تا کف بعدی؛ بیشترین رشد = بزرگ‌ترین افزایش از یک کف قبلی تا قلهٔ بعدی، هر دو درون بازه.</li><li>فاصلهٔ بیش از ۳ روز میان دو نقطه «شکاف داده» شمرده و گزارش می‌شود. هر آمار گذشته‌نگر است و پیش‌بینی نیست.</li></ul></section>
<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/prices.html">همه قیمت‌ها</a> · <a href="/transparency.html">شفافیت و اعتبار داده‌ها</a> · <a href="/analysis.html">تحلیل بازار</a> · <a href="/about.html">درباره بازارنما و روش کار</a></footer>
</main>"""

JS = r"""<script>
/*STATS*/
function stats(pts){if(!pts||pts.length<2)return null;const v=pts.map(p=>p.price),n=v.length;let min=v[0],max=v[0];for(const x of v){if(x<min)min=x;if(x>max)max=x}
const r=[];for(let i=1;i<n;i++)if(v[i-1]>0)r.push((v[i]/v[i-1]-1)*100);const mean=r.reduce((a,b)=>a+b,0)/(r.length||1);
const vol=r.length>1?Math.sqrt(r.reduce((a,b)=>a+(b-mean)**2,0)/(r.length-1)):null;
let peak=v[0],dd=0,tr=v[0],ru=0;for(const x of v){if(x>peak)peak=x;if(peak>0)dd=Math.min(dd,(x/peak-1)*100);if(x<tr)tr=x;if(tr>0)ru=Math.max(ru,(x/tr-1)*100)}
let gaps=0;for(let i=1;i<n;i++)if(pts[i].timestamp-pts[i-1].timestamp>3*86400)gaps++;
return{start:v[0],end:v[n-1],change:v[0]>0?(v[n-1]/v[0]-1)*100:null,min,max,vol,maxDrop:dd,maxRise:ru,gaps,count:n}}
function windowPts(pts,days){if(!pts||!pts.length)return[];if(!days)return pts;const cut=pts[pts.length-1].timestamp-days*86400;return pts.filter(p=>p.timestamp>=cut)}
if(typeof module!=='undefined')module.exports={stats,windowPts};
/*END*/
(()=>{if(typeof document==='undefined')return;
const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg',COL=['#087e6e','#c0392b','#2e6fd1','#b8860b','#8e44ad','#555'];
const RANGES=[['۳۰ روز',30],['۹۰ روز',90],['۶ ماه',182],['یک سال',365],['تمام تاریخچه',0]];
const STFA={fresh:'به‌روز',aging:'در آستانهٔ تأخیر',stale:'قدیمی',unknown:'نامشخص'};
let items=[],sel=['usd','btc','gold-18k'],days=90;const cache={};
const fmt=(x,d=2)=>x==null||!isFinite(x)?'نامشخص':x.toLocaleString('en-US',{maximumFractionDigits:d});
const el=(t,txt,cls)=>{const e=document.createElement(t);if(txt!=null)e.textContent=txt;if(cls)e.className=cls;return e};
async function getJSON(u){const r=await fetch(u,{cache:'no-cache'});if(!r.ok)throw new Error(u+' '+r.status);return r.json()}
function heat(){const h=$('heat');h.textContent='';let n=0;for(const i of items){const c=i.change_pct,a=el('a',null,(typeof c==='number'?(c>0?'up':c<0?'down':''):'')+((i.freshness||{}).status!=='fresh'?' old':''));a.href='/price-'+encodeURIComponent(i.id)+'.html';a.append(el('b',(i.name||{}).fa||i.id),el('small',typeof c==='number'?(c>0?'+':'')+fmt(c)+'٪':'نامشخص'),el('small',STFA[(i.freshness||{}).status]||'نامشخص'));h.append(a);n++}
$('heatNote').textContent=n?'':'داده‌ای برای نمایش وجود ندارد.'}
function chips(){const A=$('assets');A.textContent='';for(const i of items){const b=el('button',(i.name||{}).fa||i.id);b.type='button';b.setAttribute('aria-pressed',sel.includes(i.id));b.onclick=()=>{const k=sel.indexOf(i.id);if(k>=0)sel.splice(k,1);else if(sel.length<6)sel.push(i.id);else $('status').textContent='حداکثر ۶ دارایی.';chips();draw()};A.append(b)}
const R=$('ranges');R.textContent='';for(const [t,d] of RANGES){const b=el('button',t);b.type='button';b.setAttribute('aria-pressed',d===days);b.onclick=()=>{days=d;chips();draw()};R.append(b)}}
async function hist(id){if(!cache[id])cache[id]=getJSON('/api/v1/history/'+encodeURIComponent(id)+'.json').then(d=>d.points||[]).catch(()=>null);return cache[id]}
async function draw(){const svg=$('chart'),T=$('stats');svg.textContent='';T.textContent='';$('notes').textContent='';$('status').textContent=sel.length?'در حال بارگذاری…':'یک دارایی انتخاب کنید.';if(!sel.length)return;
const data=await Promise.all(sel.map(async id=>({id,pts:windowPts(await hist(id),days),failed:(await hist(id))===null})));
const ok=data.filter(d=>d.pts.length>=2),bad=data.filter(d=>d.pts.length<2);
$('status').textContent=bad.length?'داده کافی نیست برای: '+bad.map(d=>((items.find(i=>i.id===d.id)||{}).name||{}).fa||d.id).join('، '):'';
if(!ok.length)return;let t0=Infinity,t1=-Infinity,lo=Infinity,hi=-Infinity;const S=ok.map(d=>{const b=d.pts[0].price,idx=d.pts.map(p=>({t:p.timestamp,y:p.price/b*100}));for(const p of idx){t0=Math.min(t0,p.t);t1=Math.max(t1,p.t);lo=Math.min(lo,p.y);hi=Math.max(hi,p.y)}return{d,idx,st:stats(d.pts)}});
const W=640,H=280,L=46,Rr=10,Tp=10,B=26,X=t=>L+(t-t0)/((t1-t0)||1)*(W-L-Rr),Y=y=>Tp+(hi-y)/((hi-lo)||1)*(H-Tp-B);
for(let k=0;k<=4;k++){const y=lo+(hi-lo)*k/4,ln=document.createElementNS(NS,'line');ln.setAttribute('x1',L);ln.setAttribute('x2',W-Rr);ln.setAttribute('y1',Y(y));ln.setAttribute('y2',Y(y));ln.setAttribute('stroke','currentColor');ln.setAttribute('opacity','.12');svg.append(ln);const tx=document.createElementNS(NS,'text');tx.setAttribute('x',L-4);tx.setAttribute('y',Y(y)+4);tx.setAttribute('text-anchor','end');tx.textContent=fmt(y,0);svg.append(tx)}
for(const [k,e] of [[t0,'start'],[t1,'end']]){const tx=document.createElementNS(NS,'text');tx.setAttribute('x',k===t0?L:W-Rr);tx.setAttribute('y',H-6);tx.setAttribute('text-anchor',k===t0?'start':'end');tx.textContent=new Date(k*1000).toISOString().slice(0,10);svg.append(tx)}
S.forEach((s,i)=>{const p=document.createElementNS(NS,'path');let dstr='';s.idx.forEach((q,j)=>{dstr+=(j?'L':'M')+X(q.t).toFixed(1)+' '+Y(q.y).toFixed(1)});p.setAttribute('d',dstr);p.setAttribute('fill','none');p.setAttribute('stroke',COL[i%COL.length]);p.setAttribute('stroke-width','2');svg.append(p)});
const hd=['دارایی','شروع','پایان','تغییر ٪','کمترین','بیشترین','نوسان روزانه ٪','بیشترین افت ٪','بیشترین رشد ٪','نقاط','شکاف'],tr=el('tr');hd.forEach(x=>tr.append(el('th',x)));T.append(tr);
S.forEach((s,i)=>{const r=el('tr'),m=items.find(x=>x.id===s.d.id)||{},st=s.st,c=el('td',((m.name||{}).fa||s.d.id));c.style.color=COL[i%COL.length];c.style.fontWeight='700';r.append(c);[st.start,st.end].forEach(v=>r.append(el('td',fmt(v))));
r.append(el('td',(st.change>0?'+':'')+fmt(st.change),st.change>0?'up':st.change<0?'down':''));[st.min,st.max].forEach(v=>r.append(el('td',fmt(v))));r.append(el('td',fmt(st.vol)),el('td',fmt(st.maxDrop),'down'),el('td',fmt(st.maxRise),'up'),el('td',String(st.count)),el('td',String(st.gaps)));T.append(r)});
const parts=[];S.forEach(s=>{if(s.st.gaps)parts.push(((items.find(x=>x.id===s.d.id)||{}).name||{}).fa+': '+s.st.gaps+' شکاف داده')});$('notes').textContent=(parts.length?'نقاط ناقص: '+parts.join('، ')+'. ':'')+'قیمت‌ها در واحد خود هر دارایی محاسبه شده‌اند؛ تغییر ٪ مستقل از واحد است.'}
(async()=>{try{const L=await getJSON('/api/v1/latest.json');items=(L.items||[]).filter(i=>i&&i.id);heat();chips();draw()}catch(e){$('heatNote').textContent='دریافت داده ممکن نشد؛ بعداً دوباره تلاش کنید.';$('status').textContent='داده‌ای برای نمایش وجود ندارد.'}})();
})();
</script>"""


def build():
    src = (ROOT / "about.html").read_text(encoding="utf-8")
    head, rest = src.split("<body>", 1)
    tail = rest[rest.index("<script>(()=>{'use strict'"):]
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": "تحلیل بازار", "url": f"{BASE}/analysis.html",
                     "inLanguage": "fa-IR", "description": DESC}, ensure_ascii=False)
    head = re.sub(r"<title>.*?</title>", lambda m: f"<title>{TITLE}</title>", head, flags=re.S)
    head = head.replace("about.html", "analysis.html")
    for k in ('name="description" content="', 'property="og:description" content="', 'name="twitter:description" content="'):
        head = re.sub("(" + re.escape(k) + ")[^\"]*", lambda m: m.group(1) + DESC, head)
    for k in ('og:title" content="', 'twitter:title" content="'):
        head = re.sub("(" + re.escape(k) + ")[^\"]*", lambda m: m.group(1) + TITLE, head)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', lambda m: f'<script type="application/ld+json">{ld}</script>',
                  head, count=1, flags=re.S)
    head = head.replace("</head>", f"<style>{CSS}</style></head>")
    (ROOT / "analysis.html").write_text(head + '<body><main class="wrap">\n' + BODY + JS + tail, encoding="utf-8")
    print("analysis.html written")


if __name__ == "__main__":
    build()
