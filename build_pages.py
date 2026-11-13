#!/usr/bin/env python3
"""Generate one SEO page per asset (price-<id>.html), about.html and sitemap.xml.
Run:  python build_pages.py   (output is committed; no build step on the server)
"""
import re, json, html, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://bazarnama.github.io"
GLASS = (ROOT / "glass.css").read_text(encoding="utf-8")
STYLE = re.search(r"<style>(.*?)</style>", (ROOT / "currency.html").read_text(encoding="utf-8"), re.S).group(1)

A = [
 ("usd","دلار آمریکا","قیمت دلار امروز","currency","تومان","دلار آمریکا پرمعامله‌ترین ارز خارجی در بازار ایران است و بسیاری از قیمت‌های دیگر، مثل سکه و طلا، همراه با تغییر آن دنبال می‌شوند."),
 ("eur","یورو","قیمت یورو امروز","currency","تومان","یورو ارز مشترک بسیاری از کشورهای اروپایی است و برای پرداخت‌ها و سفرهای اروپایی بیشتر از دلار مورد توجه قرار می‌گیرد."),
 ("gbp","پوند انگلیس","قیمت پوند امروز","currency","تومان","پوند استرلینگ ارز رسمی بریتانیا است و معمولاً از یورو و دلار گران‌تر معامله می‌شود."),
 ("aed","درهم امارات","قیمت درهم امروز","currency","تومان","درهم امارات به دلیل مراودات تجاری و مسافرتی با امارات، یکی از ارزهای پرتقاضا در بازار ایران است."),
 ("usdt","تتر","قیمت تتر امروز","currency","تومان","تتر (USDT) رمزارزی است که قیمتش به دلار آمریکا وابسته است و در ایران بسیار برای خرید و فروش ارز دیجیتال و جایگزین دلار استفاده می‌شود."),
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
CAT = {"currency":"/currency.html","gold":"/gold.html","crypto":"/crypto.html","energy":"/energy.html"}
CATN = {"currency":"قیمت ارز","gold":"طلا و سکه","crypto":"ارز دیجیتال","energy":"نفت و انرژی"}

HEAD_COMMON = '<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icon-192.png">'
SW = "<script>if('serviceWorker' in navigator)addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}))</script>"
THEME = """const root=document.documentElement,btn=document.getElementById('themeBtn');
function ap(t,s){root.dataset.theme=t;root.style.colorScheme=t;if(btn)btn.textContent=t==='dark'?'☀':'☾';if(s){try{localStorage.setItem('bazarnama-theme',JSON.stringify(t))}catch(e){}}}
let st=null;try{st=JSON.parse(localStorage.getItem('bazarnama-theme'))}catch(e){}
ap(st||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'),false);
if(btn)btn.onclick=()=>ap(root.dataset.theme==='dark'?'light':'dark',true);"""
FOOT = '<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/currency.html">قیمت ارز</a> · <a href="/gold.html">قیمت طلا و سکه</a> · <a href="/crypto.html">قیمت ارز دیجیتال</a> · <a href="/energy.html">نفت و انرژی</a> · <a href="/prices.html">همه قیمت‌ها</a> · <a href="/about.html">درباره بازارنما و روش کار</a></footer>'
TOP = '<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>'
EXTRA_CSS = ".bni{display:inline-grid;place-items:center;width:var(--s,40px);height:var(--s,40px);flex:0 0 var(--s,40px);border-radius:50%;background:radial-gradient(circle at 30% 22%,rgba(255,255,255,.38),transparent 55%),linear-gradient(150deg,var(--a),var(--b));color:#fff;box-shadow:0 5px 12px color-mix(in srgb,var(--b) 33%,transparent),inset 0 1px 0 #ffffff66}.bni svg{width:62%;height:62%;display:block}"
EXTRA_CSS += ".kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:14px}.kv div{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:10px 14px}.kv small{display:block;color:var(--muted)}.kv b{font-size:20px}.up{color:#0a8a4a}.down{color:#c0392b}.rel{display:flex;flex-wrap:wrap;gap:8px}.rel a{border:1px solid var(--line);border-radius:999px;padding:3px 13px;text-decoration:none;color:var(--text);background:var(--surface)}"


def page(title, desc, path, body, ld, script=""):
    url = BASE + path
    e = html.escape
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{e(desc)}"><meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{url}"><meta name="theme-color" content="#087e6e">
<meta property="og:type" content="website"><meta property="og:locale" content="fa_IR"><meta property="og:site_name" content="بازارنما"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="https://bazarnama.github.io/og-image.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:image" content="https://bazarnama.github.io/og-image.png"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">
<title>{e(title)}</title>{HEAD_COMMON}
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>{STYLE}{EXTRA_CSS}</style><style id="glass">{GLASS}</style></head><body><main class="wrap">
{TOP}
{body}
{FOOT}
</main><script>(()=>{{'use strict';{THEME}{script}}})();</script>{SW}</body></html>
"""


ASSET_JS = """const ID=__ID__,UNITS={IRT:'تومان',IRR:'ریال',USD:'دلار',USDT:'تتر'};
const fmt=(v,d)=>new Intl.NumberFormat('fa-IR-u-nu-latn',{maximumFractionDigits:d??(v<10?4:v<1000?2:0)}).format(v);
const $=id=>document.getElementById(id);
function tl(v){if(!v)return 'نامشخص';const s=String(v),hasZone=/[zZ]|[+-]\\d{2}:?\\d{2}$/.test(s),d=new Date(typeof v==='number'?(v>1e12?v:v*1000):(hasZone?s:s+'Z'));return isNaN(d)?s:d.toLocaleString('fa-IR-u-nu-latn',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'}).replace(/[,،]\\s*/,' ساعت ');}
async function mergeDirectCurrencies(data){
 if(!data||!Array.isArray(data.items))return data;
 const symbols={usd:'USD_IRR_FREE',eur:'EUR_IRR_FREE',gbp:'GBP_IRR_FREE',aed:'AED_IRR_FREE'};
 try{
  const r=await fetch('https://raw.githubusercontent.com/iran-market/iran-market.github.io/main/data/popular.json?x='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw Error('secondary source unavailable');
  const payload=await r.json(),rows=Array.isArray(payload.data)?payload.data:[];
  for(const [id,symbol] of Object.entries(symbols)){
   const row=rows.find(x=>String(x?.symbol||x?.id||'').toUpperCase()===symbol);
   const price=Number(row?.price),raw=row?.updated_utc||row?.updated_at||row?.timestamp||payload.generated_utc||payload.updated_at;
   const stamp=typeof raw==='number'?(raw>1e12?raw:raw*1000):(raw?Date.parse(/[zZ]|[+-][0-9]{2}:?[0-9]{2}$/.test(String(raw))?String(raw):String(raw)+'Z'):NaN);
   const fresh=Number.isFinite(stamp)&&Date.now()-stamp<2*60*60*1000&&Date.now()-stamp>-5*60*1000&&Number.isFinite(price)&&price>0;
   const at=data.items.findIndex(x=>x.id===id),primary=at>=0?data.items[at]:null;
   if(fresh){
    const direct={...(primary||{}),id,price,unit:'IRT',source_name:'Iran Market Data',source_updated_utc:new Date(stamp).toISOString(),source:'Iran Market Data',stale:false,method:'direct'};
    if(!primary||primary.stale||primary.derived){if(at>=0)data.items[at]=direct;else data.items.push(direct);}
    else {primary.source_name=primary.source_name||'NerkhAra';primary.source_updated_utc=primary.source_updated_utc||primary.updated_utc;primary.secondary_source='Iran Market Data';primary.secondary_price=price;primary.source_discrepancy_pct=primary.price?Math.abs(primary.price-price)/primary.price*100:null;}
   }else if(['eur','gbp','aed'].includes(id)&&primary&&primary.derived){data.items.splice(at,1);}
  }
 }catch(e){
  data.items=data.items.filter(x=>!(['eur','gbp','aed'].includes(x.id)&&x.derived));
 }
 return data;
}
async function getPrices(early){
 let old=null;
 try{const r=await fetch('/data/prices.json?x='+Date.now(),{cache:'no-store'});if(r.ok){const d=await r.json();if(d&&Array.isArray(d.items)&&d.items.length){old=d;if(early)early(d);if(d.primary_ok!==false&&d.fetched_utc&&Date.now()-Date.parse(d.fetched_utc)<25*60*1000)return d;}}}catch(e){}
 try{const c=new AbortController(),t=setTimeout(()=>c.abort(),4000);try{const r=await fetch('https://nerkhara.com/api/v1/latest.json?refresh='+Date.now(),{cache:'no-store',signal:c.signal});if(!r.ok)throw Error();return await r.json();}finally{clearTimeout(t);}}
 catch(e){if(old)return {...old,items:old.items.map(i=>({...i,stale:true}))};throw e;}
}
async function load(){
 try{
  $('status').textContent='در حال دریافت نرخ…';const data=await getPrices();show(data,false);
 }catch(e){$('status').textContent='دریافت قیمت ناموفق بود؛ بعداً دوباره تلاش کن.';}
}
function show(data,early){
 try{
  const x=(data.items||[]).find(i=>i&&i.id===ID);
  let aged=false;if(x&&x.freshness&&x.freshness.observed_utc&&x.freshness.max_age_seconds>0&&Date.now()-Date.parse(x.freshness.observed_utc)>x.freshness.max_age_seconds*1000){x.stale=true;aged=true;}
  if(!x||typeof x.price!=='number'){$('price').textContent='ناموجود';$('status').textContent='قیمت معتبر از منابع دریافت نشد.';return;}
  $('price').textContent=fmt(x.price);LAST=x.price;renderReturns();$('unit').textContent=UNITS[x.unit]||x.unit||'—';
  if(typeof x.change_pct==='number'){const c=x.change_pct;$('chg').textContent='\\u2066'+(c>0?'▲ +':c<0?'▼ ':'• ')+fmt(c,2)+'٪\\u2069';$('chg').className=c>0?'up':c<0?'down':'';}else $('chg').textContent='نامشخص';
  $('time').textContent=tl(x.source_updated_utc||x.updated_utc||x.as_of);
  const source=x.source_name||x.source||'NerkhAra';
  $('sourceInfo').textContent='منبع: '+source+' · زمان آخرین به‌روزرسانی منبع: '+tl(x.source_updated_utc||x.updated_utc||x.as_of)+(x.stale?' · داده قدیمی؛ نرخ زنده نیست':'');
  $('status').textContent=early?'در حال دریافت نرخ زنده‌تر…':aged?'زمان آخرین به‌روزرسانی منبع از سقف تازگی این دارایی گذشته است؛ این داده قدیمی است و نباید نرخ زنده تلقی شود.':x.stale?'اتصال به منبع برقرار نشد؛ این آخرین داده ذخیره‌شده است و نباید نرخ زنده تلقی شود.':'قیمت با موفقیت دریافت شد.';
 }catch(e){$('status').textContent='دریافت قیمت ناموفق بود؛ بعداً دوباره تلاش کن.';}
}
let rangeDays=30,LAST=null,ALLPTS=[];
function renderReturns(){
 const amt=Number($('retAmount').value)||0,hint=$('retHint'),u=$('unit').textContent||'';let any=false;
 document.querySelectorAll('[data-ret]').forEach(el=>{
  const d=Number(el.dataset.ret),target=Date.now()/1000-d*86400;
  const cand=ALLPTS.filter(p=>p.t<=target+43200);
  const ref=cand.length?cand[cand.length-1]:null;
  if(!ref||!LAST||ALLPTS[0].t>target+86400){el.textContent='داده کافی نیست';el.className='';return;}
  const pct=(LAST-ref.v)/ref.v*100,cost=amt*ref.v,val=amt*LAST;any=true;
  el.className=pct>0?'up':pct<0?'down':'';
  el.innerHTML='\\u2066'+(pct>0?'+':'')+fmt(pct,1)+'٪\\u2069'+'<span style="display:block;font-size:13px;font-weight:400;color:var(--muted)">خرید: '+fmt(cost,0)+' '+u+'<br>الان: '+fmt(val,0)+' '+u+'</span>';
 });
 hint.textContent=any?'قیمت‌ها به واحد '+u+' است؛ کارمزد و تفاوت قیمت خرید و فروش لحاظ نشده است.':'';
}
$('retAmount').addEventListener('input',renderReturns);
$('shareBtn').addEventListener('click',async()=>{
 const url=location.origin+location.pathname,txt=document.title.split('|')[0].trim()+(LAST?' — '+fmt(LAST)+' '+($('unit').textContent||''):''),m=$('shareMsg');
 try{if(navigator.share){await navigator.share({title:document.title,text:txt,url});return;}}catch(e){if(e&&e.name==='AbortError')return;}
 try{await navigator.clipboard.writeText(txt+'\\n'+url);m.textContent='لینک کپی شد.';}catch(e){m.textContent=url;}
 setTimeout(()=>{m.textContent='';},4000);
});
function parsePoints(payload){
 let rows=payload?.points||payload?.data||payload?.history||[];
 if(!Array.isArray(rows)&&Array.isArray(payload?.series?.[ID]))rows=payload.series[ID];
 if(!Array.isArray(rows))return [];
 return rows.map(r=>{
  if(Array.isArray(r))return {t:Number(r[0]),v:Number(r[1])};
  const raw=r.timestamp??r.time??r.date??r.day;
  const t=typeof raw==='number'?(raw>1e12?raw/1000:raw):Date.parse(String(raw).length===10?String(raw)+'T00:00:00Z':(/[zZ]|[+-]\\d{2}:?\\d{2}$/.test(String(raw))?String(raw):String(raw)+'Z'))/1000;
  return {t,v:Number(r.price??r.value??r.close??r.rate)};
 }).filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.v)&&p.v>0).sort((a,b)=>a.t-b.t);
}
async function loadHistory(){
 const hint=$('chartHint');hint.textContent='در حال دریافت تاریخچه…';
 try{
  let points=[];
  try{const r=await fetch('/api/v1/history/'+encodeURIComponent(ID)+'.json?x='+Date.now(),{cache:'no-store'});if(r.ok)points=parsePoints(await r.json());}catch(e){}
  if(!points.length){
   try{const r=await fetch('/data/history.json?x='+Date.now(),{cache:'no-store'});if(r.ok){const j=await r.json();points=parsePoints({points:j?.series?.[ID]||[]});}}catch(e){}
  }
  if(!points.length){const r=await fetch('https://nerkhara.com/api/v1/history/'+encodeURIComponent(ID)+'.json',{cache:'no-store'});if(r.ok)points=parsePoints(await r.json());}
  const cutoff=rangeDays?Date.now()/1000-rangeDays*86400:0;
  ALLPTS=points.slice();renderReturns();
  points=points.filter(p=>p.t>=cutoff);
  drawHistory(points);
 }catch(e){hint.textContent='تاریخچه برای این دارایی فعلاً در دسترس نیست.';const c=$('historyChart');c.getContext('2d').clearRect(0,0,c.width,c.height);}
}
let HP=null;
(function(){try{const c=$('historyChart');if(!c)return;const wrap=document.createElement('div');wrap.style.position='relative';c.parentNode.insertBefore(wrap,c);wrap.appendChild(c);c.style.touchAction='pan-y';const tip=document.createElement('div');tip.className='chartTip';wrap.appendChild(tip);
 const show=ev=>{if(!HP)return;const r=c.getBoundingClientRect(),x=ev.clientX-r.left;let k=0,bd=1e9;HP.xy.forEach((p,i)=>{const d=Math.abs(p.x-x);if(d<bd){bd=d;k=i;}});const p=HP.xy[k],q=HP.points[k];tip.innerHTML='<b>'+fmt(q.v)+'</b>'+new Date(q.t*1000).toLocaleDateString('fa-IR-u-nu-latn');tip.classList.add('on');const tw=tip.offsetWidth;tip.style.left=Math.max(0,Math.min(r.width-tw,p.x-tw/2))+'px';tip.style.top=Math.max(0,p.y-60)+'px';};
 c.addEventListener('pointermove',show);c.addEventListener('pointerdown',show);c.addEventListener('pointerleave',()=>tip.classList.remove('on'));}catch(e){}})();
function drawHistory(points){
 const canvas=$('historyChart'),ctx=canvas.getContext('2d'),w=canvas.clientWidth||700,h=260,dpr=window.devicePixelRatio||1;
 canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);HP=null;
 if(points.length<2){$('chartHint').textContent=points.length?'برای رسم نمودار حداقل دو نقطه لازم است.':'داده تاریخی در دسترس نیست.';return;}
 const cs=getComputedStyle(document.body),muted=cs.getPropertyValue('--muted')||'#777',lineC=cs.getPropertyValue('--line')||'#ddd',brand=(cs.getPropertyValue('--brand')||'#087e6e').trim();
 const vals=points.map(p=>p.v),min=Math.min(...vals),max=Math.max(...vals),pad={l:58,r:14,t:16,b:32},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b,span=max-min||Math.max(1,max*.01);
 ctx.font='11px sans-serif';ctx.strokeStyle=lineC;ctx.fillStyle=muted;ctx.lineWidth=1;ctx.setLineDash([2,5]);
 for(let i=0;i<4;i++){const y=pad.t+ch*i/3;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();ctx.textAlign='right';ctx.fillText(fmt(max-span*i/3),pad.l-8,y+4);}
 ctx.setLineDash([]);
 const xy=points.map((p,i)=>({x:pad.l+cw*i/(points.length-1),y:pad.t+ch-(p.v-min)/span*ch}));
 if(/^#[0-9a-f]{6}$/i.test(brand)){const g=ctx.createLinearGradient(0,pad.t,0,pad.t+ch);g.addColorStop(0,brand+'30');g.addColorStop(1,brand+'00');ctx.beginPath();xy.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.lineTo(xy[xy.length-1].x,pad.t+ch);ctx.lineTo(xy[0].x,pad.t+ch);ctx.closePath();ctx.fillStyle=g;ctx.fill();}
 ctx.beginPath();xy.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));
 ctx.strokeStyle=brand;ctx.lineWidth=2;ctx.lineJoin='round';ctx.lineCap='round';ctx.stroke();
 const e=xy[xy.length-1];ctx.beginPath();ctx.arc(e.x,e.y,3.5,0,6.2832);ctx.fillStyle=brand;ctx.fill();ctx.lineWidth=2;ctx.strokeStyle='rgba(255,255,255,.85)';ctx.stroke();
 HP={xy,points};
 ctx.fillStyle=muted;ctx.textAlign='left';ctx.fillText(new Date(points[0].t*1000).toLocaleDateString('fa-IR-u-nu-latn'),pad.l,h-8);ctx.textAlign='right';ctx.fillText(new Date(points[points.length-1].t*1000).toLocaleDateString('fa-IR-u-nu-latn'),w-pad.r,h-8);
 const delta=(points[points.length-1].v/points[0].v-1)*100;
 $('chartHint').textContent=fmt(points.length)+' نقطه تاریخی · تغییر بازه: '+'\\u2066'+(delta>0?'+':'')+fmt(delta,2)+'٪\\u2069';
}
document.querySelectorAll('[data-range]').forEach(btn=>btn.addEventListener('click',()=>{rangeDays=Number(btn.dataset.range);document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',b===btn));loadHistory();}));
load();loadHistory();setInterval(load,5*60*1000);
"""


DIGITS_JS = r'''<script id="latin-digits">/* Latin digits everywhere, also for text that arrives later (news headlines, API text) */
(()=>{const M={'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9','٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'},T=/[۰-۹٠-٩]/,G=/[۰-۹٠-٩]/g,f=s=>s.replace(G,c=>M[c]);
function walk(n){if(n.nodeType===3){if(T.test(n.nodeValue))n.nodeValue=f(n.nodeValue);return;}if(n.nodeType!==1||/^(SCRIPT|STYLE|TEXTAREA)$/.test(n.nodeName))return;for(const c of n.childNodes)walk(c);}
walk(document.body);
new MutationObserver(ms=>{for(const m of ms){if(m.type==='characterData'){if(T.test(m.target.nodeValue))m.target.nodeValue=f(m.target.nodeValue);}else m.addedNodes.forEach(walk);}}).observe(document.body,{childList:true,subtree:true,characterData:true});
document.addEventListener('input',e=>{const t=e.target;if(t&&t.nodeName==='INPUT'&&t.type!=='number'&&T.test(t.value)){const p=t.selectionStart;t.value=f(t.value);try{t.setSelectionRange(p,p);}catch(x){}}});
})();</script>
'''
TR = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


GOATCOUNTER = ''  # کد GoatCounter (مثلاً 'bazarnama')؛ خالی = بدون آمار


def finalize(t):
    """All digits Latin + the small script that keeps later-arriving text Latin too."""
    t = t.translate(TR).replace("toLocaleDateString('fa-IR')", "toLocaleDateString('fa-IR-u-nu-latn')")
    if 'id="latin-digits"' not in t and "</body>" in t:
        t = t.replace("</body>", DIGITS_JS + "</body>", 1)
    if GOATCOUNTER and "goatcounter" not in t and "</body>" in t:
        t = t.replace("</body>", f'<script data-goatcounter="https://{GOATCOUNTER}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script></body>', 1)
    return t


CONTENT = {
"usd": {
"overview":"نرخ دلار در بازار آزاد ایران معمولاً به‌عنوان یکی از شاخص‌های مهم انتظارات ارزی دنبال می‌شود. عدد این صفحه قیمت ثبت‌شده برای دلار آمریکا را نشان می‌دهد؛ نرخ خرید و فروش واقعی ممکن است با توجه به شهر، زمان، حجم معامله و شرایط بازار متفاوت باشد.",
"drivers":"عرضه و تقاضای ارز، سیاست‌های ارزی و پولی، اخبار اقتصادی و سیاسی، محدودیت‌های مبادلاتی و انتظارات فعالان بازار می‌توانند بر نرخ دلار اثر بگذارند. هیچ‌کدام از این عوامل به‌تنهایی جهت یا اندازه تغییر بعدی را قطعی نمی‌کنند.",
"reading":"پیش از مقایسه نرخ‌ها، واحد تومان را بررسی کن و زمان آخرین داده را با زمان مشاهده تطبیق بده. تغییر روزانه، اگر از منبع دریافت شده باشد، فقط تغییر همان بازه گزارش‌شده است و پیش‌بینی آینده نیست.",
"faq":[("قیمت دلار این صفحه به چه واحدی است؟","قیمت با واحد تومان نمایش داده می‌شود؛ هنگام مقایسه با منابع دیگر مطمئن شو آن منبع قیمت را به تومان اعلام کرده باشد، نه ریال."),("چرا نرخ دلار در منابع مختلف فرق دارد؟","زمان به‌روزرسانی، نوع نرخ، بازار مرجع و روش گردآوری داده می‌تواند باعث اختلاف شود. زمان و منبع درج‌شده کنار قیمت را هم بررسی کن.") ]},
"eur": {
"overview":"یورو واحد پول مشترک بسیاری از کشورهای اروپایی است. نرخ یورو در بازار ایران هم از شرایط بازار ارز داخلی اثر می‌گیرد و هم از ارزش یورو در برابر ارزهای بین‌المللی؛ بنابراین تغییر آن الزاماً هم‌اندازه تغییر دلار نیست.",
"drivers":"نرخ برابری EUR/USD، سیاست‌های بانک مرکزی اروپا و فدرال رزرو، داده‌های اقتصادی منطقه یورو، تقاضای حواله و سفر و وضعیت عرضه ارز در بازار داخلی از عوامل اثرگذار هستند.",
"reading":"برای تحلیل تغییر یورو، نرخ آن را در کنار دلار و نرخ برابری جهانی یورو به دلار بررسی کن. تفاوت ساعت ثبت داده‌ها می‌تواند مقایسه دو نرخ را گمراه‌کننده کند.",
"faq":[("آیا قیمت یورو فقط به دلار وابسته است؟","خیر. نرخ جهانی یورو در برابر دلار یکی از عوامل است، اما عرضه و تقاضای یورو در بازار داخلی نیز اثر دارد."),("چرا تغییر یورو با دلار یکسان نیست؟","چون علاوه بر شرایط بازار داخلی، ارزش جهانی یورو در برابر دلار نیز تغییر می‌کند.") ]},
"gbp": {
"overview":"پوند استرلینگ واحد پول بریتانیاست. نرخ پوند در بازار ایران از شرایط عرضه و تقاضای داخلی و همچنین ارزش جهانی پوند در برابر دلار تأثیر می‌پذیرد؛ به همین دلیل مقایسه آن با یورو یا دلار باید با توجه به زمان داده انجام شود.",
"drivers":"تصمیم‌های بانک مرکزی انگلستان، تورم و رشد اقتصادی بریتانیا، نرخ برابری GBP/USD، تحولات سیاسی و تجاری و میزان تقاضای داخلی برای پوند می‌توانند بر قیمت اثر بگذارند.",
"reading":"عدد این صفحه را با واحد تومان بخوان. برای بررسی روند، چند مشاهده در بازه‌های زمانی یکسان را مقایسه کن و از نتیجه‌گیری بر اساس یک تغییر کوتاه‌مدت خودداری کن.",
"faq":[("پوند مربوط به کدام کشور است؟","پوند استرلینگ واحد پول رسمی بریتانیاست."),("چه چیزی باعث اختلاف قیمت پوند با دلار می‌شود؟","علاوه بر وضعیت بازار ارز ایران، تغییر ارزش جهانی پوند در برابر دلار و شرایط اقتصادی بریتانیا مؤثر است.") ]},
"aed": {
"overview":"درهم امارات به دلیل ارتباط تجاری، سفر و حواله‌های مالی با امارات در بازار ایران اهمیت دارد. درهم امارات به دلار آمریکا نرخ برابری ثابتی نزدیک دارد، اما نرخ آن در بازار داخلی می‌تواند تحت تأثیر شرایط عرضه و تقاضا و هزینه دسترسی قرار بگیرد.",
"drivers":"تقاضای تجاری و مسافرتی، جریان حواله، شرایط نقل‌وانتقال پول، نرخ دلار در بازار داخلی و اختلاف قیمت خرید و فروش از عوامل مهم در نرخ درهم هستند.",
"reading":"هنگام مقایسه، دقت کن که قیمت مربوط به درهم امارات و با واحد تومان باشد. نرخ صرافی، حواله و اسکناس ممکن است یکسان نباشد.",
"faq":[("آیا درهم همیشه دقیقاً با دلار حرکت می‌کند؟","درهم به دلار آمریکا پیوند ارزی دارد، اما نرخ مشاهده‌شده در بازار ایران می‌تواند به دلیل عرضه، تقاضا و هزینه معامله متفاوت باشد."),("قیمت درهم برای حواله و اسکناس یکی است؟","نه لزوماً؛ نوع معامله و هزینه انتقال می‌تواند باعث تفاوت نرخ شود.") ]},
"usdt": {
"overview":"تتر با نماد USDT یک دارایی دیجیتال با هدف حفظ ارزش نزدیک به یک دلار آمریکا است. قیمت تتر در بازار ایران معمولاً به نرخ دلار داخلی، وضعیت عرضه و تقاضای رمزارز و شرایط پلتفرم‌های معاملاتی وابسته است؛ بنابراین الزاماً برابر با یک دلار ضرب‌در نرخ رسمی یا آزاد نیست.",
"drivers":"قیمت جهانی USDT در برابر دلار، عمق بازار صرافی‌ها، تقاضای تبدیل ریال به رمزارز، کارمزد و محدودیت‌های واریز و برداشت و شرایط شبکه انتقال می‌توانند بر نرخ تتر اثر بگذارند.",
"reading":"هنگام مشاهده قیمت، واحد آن را بررسی کن؛ نرخ تتر ممکن است به تومان یا ریال نمایش داده شود. قیمت خرید و فروش در صرافی‌ها نیز به دلیل اختلاف سفارش‌ها و کارمزد یکسان نیست.",
"faq":[("آیا قیمت تتر همیشه دقیقاً یک دلار است؟","هدف طراحی تتر حفظ ارزش نزدیک به یک دلار است، اما ممکن است در بازارها برای مدتی با اختلافی بالاتر یا پایین‌تر معامله شود."),("چرا قیمت تتر با دلار تفاوت دارد؟","بازار رمزارز، تقاضای تبدیل، نقدشوندگی، کارمزد و شرایط انتقال می‌توانند باعث اختلاف شوند.") ]},
"gold-18k": {
"overview":"طلای ۱۸ عیار از رایج‌ترین معیارهای اعلام قیمت طلا در بازار ایران است. هر گرم طلای ۱۸ عیار از نظر خلوص ۷۵ درصد طلا دارد. قیمت خام هر گرم با قیمت نهایی زیورآلات تفاوت دارد؛ اجرت ساخت، سود فروشنده و مالیات‌های مربوط می‌توانند به مبلغ پرداختی اضافه شوند.",
"drivers":"قیمت جهانی اونس طلا، نرخ ارز، انتظارات تورمی، تقاضای داخلی و شرایط بازار طلا بر نرخ هر گرم اثر می‌گذارند. تغییر هر عامل ممکن است اثر متفاوتی بر قیمت داخلی داشته باشد.",
"reading":"عدد نمایش‌داده‌شده را قیمت هر گرم با واحد تومان در نظر بگیر. برای برآورد هزینه خرید زیورآلات، فقط به نرخ خام اکتفا نکن و اجرت، سود و مالیات اعلام‌شده فروشنده را جداگانه بررسی کن.",
"faq":[("طلای ۱۸ عیار یعنی چه؟","یعنی از ۲۴ بخش وزنی آلیاژ، ۱۸ بخش آن طلاست؛ در نتیجه خلوص آن ۷۵ درصد است."),("آیا قیمت این صفحه همان مبلغ خرید طلا از طلافروشی است؟","خیر. قیمت خام هر گرم با مبلغ نهایی زیورآلات که می‌تواند شامل اجرت، سود و مالیات باشد تفاوت دارد.") ]},
"coin-emami": {
"overview":"سکه امامی یکی از سکه‌های رایج و پرمعامله بازار ایران است. قیمت آن فقط از ارزش طلای به‌کاررفته تشکیل نمی‌شود؛ میزان عرضه و تقاضا و فاصله قیمت بازار با ارزش ذاتی نیز در نرخ معامله نقش دارد.",
"drivers":"قیمت اونس جهانی، نرخ ارز، ارزش ذاتی طلای سکه، انتظارات تورمی، تقاضای فصلی و حباب بازار از عوامل مؤثر بر قیمت سکه امامی هستند.",
"reading":"برای مقایسه سکه، علاوه بر قیمت روز، حباب و اختلاف قیمت خرید و فروش را هم در نظر بگیر. قیمت درج‌شده در این صفحه نرخ مرجع داده است و ممکن است با پیشنهاد معامله‌گر تفاوت داشته باشد.",
"faq":[("حباب سکه چیست؟","حباب به فاصله قیمت بازار سکه از ارزش تقریبی طلای موجود در آن گفته می‌شود؛ این فاصله می‌تواند مثبت یا منفی باشد."),("آیا قیمت سکه فقط با اونس طلا تغییر می‌کند؟","خیر. نرخ ارز و شرایط عرضه و تقاضای داخلی نیز می‌توانند اثر قابل‌توجهی داشته باشند.") ]},
"coin-half": {
"overview":"نیم‌سکه یکی از قطعات شناخته‌شده سکه بهار آزادی در بازار ایران است. با وجود وزن کمتر نسبت به سکه تمام، قیمت آن همیشه دقیقاً نصف قیمت سکه امامی نیست؛ زیرا تقاضا، نقدشوندگی و حباب هر قطعه می‌تواند متفاوت باشد.",
"drivers":"ارزش طلای سکه، نرخ ارز، قیمت اونس جهانی، میزان عرضه، تقاضای خریداران و فاصله قیمت بازار با ارزش ذاتی بر نرخ نیم‌سکه اثر دارند.",
"reading":"برای مقایسه نیم‌سکه با سکه تمام، نسبت قیمت‌ها را در یک زمان واحد بررسی کن. اختلاف قیمت خرید و فروش و حباب قطعه را نیز نادیده نگیر.",
"faq":[("آیا نیم‌سکه نصف قیمت سکه امامی است؟","نه لزوماً؛ حباب و شرایط عرضه و تقاضای هر قطعه می‌تواند باعث شود نسبت قیمت‌ها دقیقاً یک‌به‌دو نباشد."),("چه عواملی قیمت نیم‌سکه را تغییر می‌دهند؟","قیمت طلا و ارز، ارزش ذاتی سکه و میزان تقاضا در بازار داخلی از عوامل مهم هستند.") ]},
"coin-quarter": {
"overview":"ربع‌سکه قطعه‌ای کوچک‌تر از سکه تمام و نیم‌سکه است. قیمت آن علاوه بر ارزش طلای موجود، از شرایط عرضه و تقاضا تأثیر می‌گیرد؛ به همین دلیل نسبت قیمت ربع‌سکه با نیم‌سکه همیشه متناسب با وزن آن نیست.",
"drivers":"اونس جهانی طلا، نرخ ارز، ارزش ذاتی قطعه، میزان عرضه، تقاضای مناسبتی و حباب بازار از عوامل اثرگذار بر قیمت ربع‌سکه هستند.",
"reading":"هنگام بررسی قیمت ربع‌سکه، آن را با نرخ نیم‌سکه و سکه تمام در یک زمان مقایسه کن. کوچک‌تر بودن وزن به‌تنهایی به معنی ارزان‌تر بودن متناسب با وزن نیست.",
"faq":[("چرا ربع‌سکه گاهی حباب بیشتری دارد؟","تقاضای خرد و محدودیت عرضه در برخی دوره‌ها می‌تواند فاصله قیمت بازار با ارزش طلای قطعه را افزایش دهد."),("آیا قیمت ربع‌سکه متناسب با یک‌چهارم سکه تمام است؟","خیر؛ حباب و شرایط بازار ممکن است نسبت قیمت را از نسبت وزن متفاوت کند.") ]},
"xau": {
"overview":"اونس جهانی طلا معیار رایج قیمت‌گذاری طلا در بازارهای بین‌المللی است. منظور از اونس در این بازار معمولاً اونس تروا با وزن تقریبی ۳۱٫۱۰۳۵ گرم است و قیمت آن به دلار برای هر اونس اعلام می‌شود.",
"drivers":"نرخ بهره واقعی، سیاست بانک‌های مرکزی، ارزش دلار آمریکا، خریدوفروش بانک‌های مرکزی، ریسک‌های اقتصادی و ژئوپلیتیکی و تقاضای سرمایه‌گذاری می‌توانند بر قیمت جهانی طلا اثر بگذارند.",
"reading":"قیمت اونس با دلار اعلام می‌شود و با قیمت هر گرم طلای ۱۸ عیار در ایران یکسان نیست. برای تبدیل تقریبی، وزن، خلوص طلا و نرخ تبدیل ارز باید جداگانه لحاظ شوند.",
"faq":[("هر اونس طلا چند گرم است؟","اونس تروا که در بازار فلزات گران‌بها استفاده می‌شود تقریباً ۳۱٫۱۰۳۵ گرم است."),("چرا اونس جهانی با قیمت طلای ایران متفاوت است؟","قیمت داخلی علاوه بر اونس، از نرخ ارز، عیار، هزینه‌ها و شرایط عرضه و تقاضای بازار ایران اثر می‌گیرد.") ]},
"btc": {
"overview":"بیت‌کوین یک دارایی دیجیتال غیرمتمرکز با عرضه کل محدودشده در پروتکل است. قیمت آن در بازارهای مختلف بر اساس سفارش‌های خریدوفروش شکل می‌گیرد و ممکن است میان صرافی‌ها و جفت‌ارزهای معاملاتی اختلاف داشته باشد.",
"drivers":"تقاضای بازار، نقدینگی صرافی‌ها، جریان سرمایه نهادی، شرایط اقتصاد کلان، مقررات، رویدادهای شبکه و احساسات معامله‌گران از عوامل اثرگذار بر نوسان بیت‌کوین هستند. نوسان گذشته تضمینی برای حرکت آینده نیست.",
"reading":"واحد نمایش این صفحه تتر است. برای مقایسه قیمت، جفت‌ارز معاملاتی، زمان ثبت داده و کارمزد صرافی را بررسی کن. قیمت دلاری یا تتری را با قیمت ریالی بدون تبدیل و توجه به نرخ ارز مقایسه نکن.",
"faq":[("قیمت بیت‌کوین در این صفحه با چه واحدی است؟","قیمت با واحد تتر (USDT) نمایش داده می‌شود؛ این عدد را با نرخ ریالی صرافی‌ها بدون تبدیل مقایسه نکن."),("چرا قیمت بیت‌کوین در صرافی‌ها فرق دارد؟","تفاوت نقدشوندگی، حجم سفارش‌ها، جفت‌ارز، زمان به‌روزرسانی و کارمزد می‌تواند اختلاف ایجاد کند.") ]},
"eth": {
"overview":"اتریوم یک شبکه بلاک‌چینی عمومی است که اجرای قراردادهای هوشمند و برنامه‌های غیرمتمرکز را ممکن می‌کند. اتر با نماد ETH دارایی بومی این شبکه است و قیمت آن در بازار رمزارزها با عرضه و تقاضا تعیین می‌شود.",
"drivers":"فعالیت کاربران و برنامه‌های شبکه، کارمزد و میزان استفاده از اتریوم، به‌روزرسانی‌های فنی، رقابت شبکه‌های دیگر، شرایط اقتصاد کلان و جریان سرمایه بازار رمزارز می‌توانند بر قیمت ETH اثر بگذارند.",
"reading":"قیمت این صفحه با واحد تتر نمایش داده می‌شود. برای مقایسه، جفت‌ارز و زمان قیمت را یکسان نگه دار و هزینه معامله و انتقال شبکه را جداگانه محاسبه کن.",
"faq":[("اتریوم و اتر چه تفاوتی دارند؟","اتریوم نام شبکه و اکوسیستم بلاک‌چین است؛ اتر (ETH) دارایی بومی آن شبکه محسوب می‌شود."),("آیا قیمت ETH فقط به بیت‌کوین وابسته است؟","خیر. شرایط کلی بازار اثر دارد، اما کاربرد شبکه، فعالیت کاربران و عوامل اختصاصی اتریوم نیز مهم‌اند.") ]},
"brent": {
"overview":"نفت برنت یکی از معیارهای اصلی قیمت‌گذاری نفت خام در بازار جهانی است و برای ارزیابی بسیاری از معاملات نفتی بین‌المللی به‌کار می‌رود. قیمت آن معمولاً به دلار برای هر بشکه اعلام می‌شود.",
"drivers":"تعادل عرضه و تقاضای جهانی، تصمیم‌های تولیدکنندگان، سطح ذخایر نفت، رشد اقتصاد جهان، اختلال‌های حمل‌ونقل و تحولات ژئوپلیتیکی از عوامل اثرگذار بر قیمت برنت هستند.",
"reading":"واحد قیمت را دلار به‌ازای هر بشکه در نظر بگیر. قیمت شاخص برنت با قیمت نهایی هر نوع نفت تحویلی یا فرآورده نفتی یکسان نیست و کیفیت و محل تحویل اهمیت دارد.",
"faq":[("نفت برنت با نفت WTI چه تفاوتی دارد؟","برنت و WTI دو شاخص مرجع متفاوت‌اند که به انواع نفت خام و بازارهای تحویل متفاوت مربوط می‌شوند."),("قیمت برنت در این صفحه برای چه واحدی است؟","قیمت بر حسب دلار به‌ازای هر بشکه نمایش داده می‌شود.") ]},
"wti": {
"overview":"WTI مخفف West Texas Intermediate و یکی از شاخص‌های مرجع نفت خام آمریکاست. این شاخص معمولاً برای مقایسه قیمت نفت خام در بازار آمریکای شمالی استفاده می‌شود و قیمت آن به دلار برای هر بشکه اعلام می‌شود.",
"drivers":"موجودی نفت خام آمریکا، ظرفیت پالایشگاه‌ها، تولید داخلی، تقاضای سوخت، وضعیت خطوط لوله و شرایط بازار جهانی نفت بر قیمت WTI اثر می‌گذارند.",
"reading":"قیمت WTI را با واحد دلار به‌ازای هر بشکه بخوان. هنگام مقایسه با برنت، زمان داده و تفاوت کیفیت و محل تحویل دو شاخص را نیز در نظر بگیر.",
"faq":[("WTI مخفف چیست؟","WTI مخفف West Texas Intermediate و نام یک شاخص مرجع نفت خام آمریکاست."),("چرا قیمت WTI با برنت فرق دارد؟","کیفیت نفت، محل تحویل، هزینه حمل‌ونقل، شرایط عرضه و تقاضای منطقه‌ای و ساختار بازار می‌توانند اختلاف قیمت ایجاد کنند.") ]},
}


QTY = {'usd':'دلار','eur':'یورو','gbp':'پوند','aed':'درهم','usdt':'تتر','gold-18k':'گرم','coin-emami':'سکه','coin-half':'نیم‌سکه','coin-quarter':'ربع‌سکه','xau':'اونس','btc':'بیت‌کوین','eth':'اتریوم','brent':'بشکه','wti':'بشکه'}


# ---- دارایی‌های افزوده‌شده: طلا، نقره، فلزات، انرژی و ارزهای دیجیتال ----
# (id, نام، عنوان صفحه، دسته، واحد قیمت، واحد مقدار، توضیح کوتاه، دربارهٔ دارایی، عوامل مؤثر)
NEW = [
 ("gold-24k","طلای 24 عیار","قیمت طلای 24 عیار امروز","gold","تومان / گرم","گرم","طلای 24 عیار خالص‌ترین عیار طلا است و برای شمش، سرمایه‌گذاری و محاسبهٔ ارزش پایهٔ طلا استفاده می‌شود.","طلای 24 عیار حدود 99.9 درصد خلوص دارد. قیمت هر گرم آن مبنای مقایسهٔ عیارهای دیگر است و معمولاً بدون اجرت ساخت و مالیات گزارش می‌شود.","قیمت جهانی اونس طلا، نرخ دلار در بازار آزاد، تقاضای سرمایه‌گذاری و فصل‌های خرید مانند عروسی یا مناسبت‌ها بر قیمت اثر می‌گذارند."),
 ("gold-mesghal","طلای آبشده (مثقال)","قیمت طلای آبشده امروز","gold","تومان / مثقال","مثقال","طلای آبشده یا مثقال طلا نرخ رایج معاملهٔ طلای ذوب‌شده در بازار است و واحد آن مثقال است.","هر مثقال حدود 4.608 گرم است. طلای آبشده در بازار با عیاری نزدیک به 750 معامله می‌شود و قیمت آن با قیمت گرم 18 عیار متفاوت است؛ مقایسه باید با توجه به واحد انجام شود.","اونس جهانی طلا، نرخ دلار، عرضه و تقاضای طلای دست‌دوم و نوسان‌های کوتاه‌مدت بازار بر نرخ مثقال اثر دارند."),
 ("coin-bahar-azadi","سکه بهار آزادی","قیمت سکه بهار آزادی امروز","gold","تومان","سکه","سکه بهار آزادی (طرح قدیم) از سکه‌های رایج بازار است و قیمت آن همراه با قیمت طلا و دلار تغییر می‌کند.","این سکه حدود 8.133 گرم طلای 900 عیار دارد. قیمت آن شامل ارزش ذاتی طلا و حباب بازار است و حباب می‌تواند با انتظارات بازار کم یا زیاد شود.","اونس جهانی طلا، نرخ دلار، انتظارات تورمی، قوانین معاملهٔ سکه و میزان تقاضا بر قیمت اثر می‌گذارند."),
 ("coin-gram","سکه گرمی","قیمت سکه گرمی امروز","gold","تومان","سکه","سکهٔ گرمی برای خرید با سرمایهٔ کم و هدیه‌دادن شناخته می‌شود و قیمت آن از طلای خام بیشتر است.","سکه‌های گرمی وزن کم دارند و بخشی از قیمتشان به هزینهٔ ضرب و بسته‌بندی برمی‌گردد؛ به همین دلیل نسبت قیمت آن‌ها به ارزش طلا از سکه‌های بزرگ‌تر بیشتر است.","قیمت طلا، نرخ دلار، تقاضای هدیه و فصل‌های خرید و هزینهٔ ضرب بر قیمت اثر می‌گذارند."),
 ("silver-999","نقره 999 (گرم)","قیمت نقره 999 امروز","gold","تومان / گرم","گرم","قیمت هر گرم نقرهٔ 999 در بازار ایران که بر پایهٔ قیمت جهانی نقره و نرخ دلار شکل می‌گیرد.","نقره 999 یعنی خلوص 99.9 درصد. نقره هم فلز سرمایه‌گذاری است و هم در صنعت (الکترونیک، پنل خورشیدی) مصرف می‌شود، به همین دلیل نوسان آن معمولاً از طلا بیشتر است.","اونس جهانی نقره، نرخ دلار، تقاضای صنعتی و رفتار بازار طلا بر قیمت نقره اثر می‌گذارند."),
 ("xag","اونس جهانی نقره","قیمت اونس جهانی نقره امروز","gold","دلار / اونس","اونس","اونس جهانی نقره قیمت هر اونس تروی (حدود 31.1 گرم) نقره در بازار جهانی است و مبنای قیمت نقره در بازارهای محلی است.","نقره یکی از فلزات گرانبها است و قیمت آن به دلار اعلام می‌شود. هم نقش پناهگاه امن دارد و هم تقاضای صنعتی.","سیاست پولی فدرال رزرو، ارزش دلار، تقاضای صنعتی، قیمت طلا و ریسک‌پذیری بازار بر قیمت جهانی نقره اثر دارند."),
 ("xpt","اونس جهانی پلاتین","قیمت اونس جهانی پلاتین امروز","gold","دلار / اونس","اونس","قیمت جهانی هر اونس پلاتین؛ فلزی گرانبها که بیشتر در صنعت خودرو و جواهرسازی مصرف می‌شود.","پلاتین کمیاب‌تر از طلا است و مصرف عمدهٔ آن در مبدل‌های کاتالیستی خودرو است؛ به همین دلیل قیمتش به صنعت خودرو حساس است.","تقاضای صنعت خودرو، عرضهٔ معدنی، ارزش دلار و قیمت سایر فلزات گرانبها بر نرخ اثر می‌گذارند."),
 ("xpd","اونس جهانی پالادیوم","قیمت اونس جهانی پالادیوم امروز","gold","دلار / اونس","اونس","قیمت جهانی هر اونس پالادیوم؛ فلزی که عمدتاً در مبدل‌های کاتالیستی خودرو استفاده می‌شود.","پالادیوم بیشتر از چند کشور محدود تولید می‌شود و قیمت آن به تولید خودروهای بنزینی و مقررات آلایندگی حساس است.","تقاضای صنعت خودرو، محدودیت‌های عرضه، ارزش دلار و قیمت فلزات دیگر بر نرخ اثر می‌گذارند."),
 ("paxg","پکس گلد (PAXG)","قیمت پکس گلد امروز","gold","تتر","PAXG","پکس گلد توکنی است که هر واحد آن به یک اونس طلای فیزیکی وابسته است و با تتر معامله می‌شود.","PAXG یک رمزارز پشتوانه‌دار طلا است؛ قیمتش معمولاً نزدیک به اونس جهانی طلا می‌ماند ولی ممکن است در بازارهای مختلف کمی اختلاف داشته باشد.","قیمت اونس جهانی طلا، نقدشوندگی بازار رمزارز و شرایط صرافی‌ها بر قیمت اثر می‌گذارند."),
 ("natural-gas","گاز طبیعی","قیمت گاز طبیعی امروز","energy","دلار / MMBtu","MMBtu","قیمت گاز طبیعی در بازار آمریکا (هنری هاب) بر حسب دلار برای هر میلیون BTU.","گاز طبیعی شاخص مهم انرژی برای گرمایش و تولید برق است و قیمت آن به فصل، ذخایر و آب‌وهوا حساس است.","میزان ذخایر ذخیره‌شده، دمای هوا، تولید و صادرات LNG و تقاضای صنعتی بر قیمت اثر می‌گذارند."),
 ("opec-basket","سبد نفتی اوپک","قیمت سبد نفتی اوپک امروز","energy","دلار / بشکه","بشکه","میانگین قیمت نفت‌های خام کشورهای عضو اوپک که برای ارزیابی بازار نفت استفاده می‌شود.","سبد اوپک میانگینی از چند نوع نفت خام اعضا است و معمولاً در بازهٔ نزدیک به برنت حرکت می‌کند.","سیاست‌های تولید اوپک، تقاضای جهانی، اخبار ژئوپلیتیک و ارزش دلار بر قیمت اثر می‌گذارند."),
 ("brent-spot","نفت برنت فیزیکی","قیمت نفت برنت فیزیکی امروز","energy","دلار / بشکه","بشکه","قیمت نقدی (فیزیکی) نفت برنت که تحویل واقعی را نشان می‌دهد و ممکن است با قرارداد آتی فرق داشته باشد.","قیمت فیزیکی نشان‌دهندهٔ معاملهٔ نفت قابل تحویل است و در زمان کمبود عرضه می‌تواند از قیمت قرارداد آتی بیشتر یا کمتر باشد.","تنگنای عرضه، هزینهٔ حمل، تقاضای پالایشگاه‌ها و اخبار ژئوپلیتیک بر قیمت اثر می‌گذارند."),
 ("wti-spot","نفت WTI فیزیکی","قیمت نفت WTI فیزیکی امروز","energy","دلار / بشکه","بشکه","قیمت نقدی نفت وست تگزاس اینترمدیت (WTI) که با قرارداد آتی آن ممکن است اختلاف داشته باشد.","قیمت فیزیکی WTI در مرکز کاشینگ آمریکا ثبت می‌شود و ذخایر آن مهم‌ترین عامل کوتاه‌مدت است.","ذخایر نفت آمریکا، تولید شیل، تقاضای پالایشگاه‌ها و ارزش دلار بر قیمت اثر می‌گذارند."),
 ("sol","سولانا (SOL)","قیمت سولانا امروز","crypto","تتر","سولانا","سولانا رمزارز یک بلاک‌چین پرسرعت برای قراردادهای هوشمند و برنامه‌های غیرمتمرکز است.","SOL توکن بومی شبکهٔ سولانا است و برای کارمزد و استیکینگ استفاده می‌شود. قیمت آن مانند سایر رمزارزها نوسان بالایی دارد.","وضعیت کلی بازار رمزارز، رشد برنامه‌های روی شبکه، به‌روزرسانی‌های فنی و جریان سرمایه بر قیمت اثر می‌گذارند."),
 ("xrp","ریپل (XRP)","قیمت ریپل امروز","crypto","تتر","ریپل","ریپل رمزارزی برای انتقال سریع و کم‌هزینهٔ پول و تسویهٔ بین‌المللی است.","XRP توکن شبکهٔ XRP Ledger است و در پرداخت‌های فرامرزی کاربرد دارد. قیمت آن به اخبار حقوقی و همکاری‌های مالی حساس است.","اخبار قانونی، همکاری با نهادهای مالی، وضعیت بازار رمزارز و نقدشوندگی بر قیمت اثر می‌گذارند."),
 ("bnb","بایننس کوین (BNB)","قیمت بایننس کوین امروز","crypto","تتر","BNB","BNB توکن بومی اکوسیستم بایننس و شبکهٔ BNB Chain است.","از BNB برای پرداخت کارمزد در شبکه و کاهش هزینهٔ معاملات در صرافی بایننس استفاده می‌شود.","وضعیت صرافی بایننس، رشد شبکهٔ BNB Chain، سوزاندن دوره‌ای توکن و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("doge","دوج‌کوین (DOGE)","قیمت دوج‌کوین امروز","crypto","تتر","دوج‌کوین","دوج‌کوین یکی از قدیمی‌ترین رمزارزهای میم است که به‌خاطر جامعهٔ بزرگ و توجه رسانه‌ای شناخته می‌شود.","DOGE ابتدا به‌شوخی ساخته شد اما حالا در بسیاری از صرافی‌ها معامله می‌شود. قیمت آن به احساسات بازار و اخبار شبکه‌های اجتماعی حساس است.","هیجان بازار، توجه رسانه‌ها، پذیرش به‌عنوان وسیلهٔ پرداخت و وضعیت کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("ltc","لایت‌کوین (LTC)","قیمت لایت‌کوین امروز","crypto","تتر","لایت‌کوین","لایت‌کوین رمزارزی قدیمی با تأیید سریع‌تر تراکنش نسبت به بیت‌کوین است.","LTC برای پرداخت‌های روزمره طراحی شده و مانند بیت‌کوین دورهٔ نصف‌شدن پاداش دارد.","رویداد نصف‌شدن، وضعیت بیت‌کوین، حجم معاملات و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("trx","ترون (TRX)","قیمت ترون امروز","crypto","تتر","ترون","ترون بلاک‌چینی برای قراردادهای هوشمند و انتقال استیبل‌کوین‌ها به‌ویژه تتر است.","بخش بزرگی از تراکنش‌های تتر روی شبکهٔ ترون انجام می‌شود و TRX برای کارمزد و منابع شبکه استفاده می‌شود.","حجم تراکنش‌های استیبل‌کوین، فعالیت شبکه و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("ada","کاردانو (ADA)","قیمت کاردانو امروز","crypto","تتر","کاردانو","کاردانو بلاک‌چین اثبات سهام (PoS) است که با رویکرد پژوهشی توسعه یافته است.","ADA توکن بومی شبکه است و برای استیکینگ، کارمزد و مشارکت در حاکمیت استفاده می‌شود.","پیشرفت فنی شبکه، رشد اکوسیستم، جریان سرمایه و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("ton","تون‌کوین (TON)","قیمت تون‌کوین امروز","crypto","تتر","تون","تون‌کوین رمزارز شبکهٔ TON است که با پیام‌رسان تلگرام ارتباط نزدیک دارد.","TON برای پرداخت کارمزد و برنامه‌های مینی‌اپ روی شبکه استفاده می‌شود؛ رشد کاربران تلگرام می‌تواند بر آن اثر بگذارد.","توسعهٔ برنامه‌های تلگرام، تعداد کاربران فعال، نقدشوندگی و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
 ("bch","بیت‌کوین کش (BCH)","قیمت بیت‌کوین کش امروز","crypto","تتر","بیت‌کوین کش","بیت‌کوین کش شاخه‌ای از بیت‌کوین با بلوک‌های بزرگ‌تر برای پرداخت‌های ارزان‌تر است.","BCH در سال 2017 از بیت‌کوین جدا شد و هدفش پرداخت‌های روزمره با کارمزد پایین است.","قیمت بیت‌کوین، پذیرش در پرداخت‌ها و وضعیت کلی بازار رمزارز بر قیمت اثر می‌گذارند."),
 ("dot","پولکادات (DOT)","قیمت پولکادات امروز","crypto","تتر","پولکادات","پولکادات پروتکلی برای اتصال چند بلاک‌چین مستقل به یکدیگر است.","DOT برای استیکینگ، حاکمیت و امنیت شبکه استفاده می‌شود و شبکه از چندین زنجیرهٔ موازی تشکیل شده است.","پیشرفت فنی، رشد پروژه‌های متصل به شبکه و بازار کلی رمزارز بر قیمت اثر می‌گذارند."),
]
for _id, _n, _h1, _cat, _unit, _q, _blurb, _about, _drv in NEW:
    A.append((_id, _n, _h1, _cat, _unit, _blurb))
    QTY[_id] = _q
    _un = "تتر" if _unit == "تتر" else ("دلار" if _unit.startswith("دلار") else "تومان")
    _tail = {"crypto": "قیمت رمزارزها در همهٔ ساعت‌ها تغییر می‌کند و ممکن است بین صرافی‌ها کمی تفاوت داشته باشد.",
             "gold": "قیمت‌ها بدون اجرت ساخت، مالیات و هزینهٔ خرید و فروش گزارش می‌شوند؛ قیمت نهایی معامله ممکن است فرق کند.",
             "energy": "این قیمت برای آگاهی عمومی است و قیمت معاملهٔ واقعی ممکن است با زمان و بازار مرجع فرق کند."}[_cat]
    CONTENT[_id] = {
        "overview": _about,
        "drivers": _drv,
        "reading": f"واحد قیمت این دارایی {_unit} است؛ هنگام مقایسه با منابع دیگر واحد و زمان آخرین داده را بررسی کن. {_tail}",
        "faq": [
            (f"قیمت {_n} به چه واحدی است؟", f"قیمت این صفحه به {_un} نمایش داده می‌شود (واحد کامل: {_unit}). هنگام مقایسه با منابع دیگر مطمئن شو همان واحد را به کار برده‌اند."),
            (f"چرا قیمت {_n} در منابع مختلف فرق دارد؟", "زمان به‌روزرسانی، بازار مرجع، نوع نرخ و روش گردآوری داده می‌تواند باعث اختلاف شود. زمان و منبع درج‌شده کنار قیمت را بررسی کن."),
        ],
    }


# ---- آیکون‌ها (منبع واحد: این بخش؛ خروجی در bn-icons.js و صفحه‌های ساخته‌شده) ----
def _t(txt, size=23, y=None):
    y = y if y is not None else (28 if size > 16 else 25)
    return f'<text x="20" y="{y}" text-anchor="middle" font-family="Arial,sans-serif" font-size="{size}" font-weight="800" fill="#fff">{txt}</text>'


_RING = '<circle cx="20" cy="20" r="12" stroke="#fff" stroke-width="2.4" fill="none"/>'
_DROP = '<path d="M20 7C20 7 10.5 17.5 10.5 24a9.5 9.5 0 0 0 19 0C29.5 17.5 20 7 20 7z" fill="#fff"/>'


def _dropl(ch, col):
    return _DROP + f'<text x="20" y="28" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" font-weight="800" fill="{col}">{ch}</text>'


_BAR = '<path d="M7.5 27 11.5 15h17l4 12z" fill="#fff" fill-opacity=".95"/><path d="M11.5 15h17l.9 2.6H10.6z" fill="#fff"/><path d="M12.5 27l2-6h11l2 6z" fill="#000" fill-opacity=".13"/>'
_STAR = '<path d="M20 12.5l2.2 5 5.4.5-4.1 3.6 1.3 5.3-4.8-2.8-4.8 2.8 1.3-5.3-4.1-3.6 5.4-.5z" fill="#fff"/>'

# id: (رنگ ۱، رنگ ۲، شکل)
ICONS = {
    "usd": ("#34c98a", "#0a7650", _t("$")), "eur": ("#5b8cff", "#1c3ea6", _t("€")),
    "gbp": ("#9b6cff", "#46269e", _t("£")), "aed": ("#19c2ae", "#0a6761", _t("د", 22)),
    "usdt": ("#35c9a6", "#12705b", _t("₮", 24)),
    "gold-18k": ("#fbdc7a", "#c48410", _BAR),
    "gold-24k": ("#ffe08a", "#b87a05", _BAR + _t("24", 9, 25).replace('fill="#fff"', 'fill="#7a4f00"')),
    "gold-mesghal": ("#f7c948", "#a66a06", '<path d="M20 7C20 7 11 17.5 11 23.5a9 9 0 0 0 18 0C29 17.5 20 7 20 7z" fill="#fff"/><path d="M14 31h12" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'),
    "coin-emami": ("#f8d35c", "#b5750a", _RING + '<circle cx="20" cy="20" r="6.6" fill="#fff"/>'),
    "coin-bahar-azadi": ("#f4c542", "#a8670a", _RING + _STAR),
    "coin-half": ("#f8d35c", "#b5750a", _RING + '<path d="M20 13.4a6.6 6.6 0 0 0 0 13.2z" fill="#fff"/>'),
    "coin-quarter": ("#f8d35c", "#b5750a", _RING + '<path d="M20 20v-6.6A6.6 6.6 0 0 0 13.4 20z" fill="#fff"/>'),
    "coin-gram": ("#f6cf55", "#ad700a", _RING + _t("g", 15, 25)),
    "xau": ("#efc24f", "#8a5805", '<circle cx="20" cy="20" r="12" stroke="#fff" stroke-width="2.2" stroke-opacity=".9" fill="none"/>' + _t("Au", 12.5)),
    "paxg": ("#e8b93a", "#7d5206", _RING + _t("PG", 11, 24)),
    "silver-999": ("#d3d9e3", "#78859a", _BAR),
    "xag": ("#cfd6e2", "#6f7d93", _RING + _t("Ag", 11.5, 24.5)),
    "xpt": ("#c3cfdf", "#56657d", _RING + _t("Pt", 11.5, 24.5)),
    "xpd": ("#b8c3d6", "#4f5c76", _RING + _t("Pd", 11.5, 24.5)),
    "btc": ("#ffa62e", "#d4680a", _t("₿", 24)),
    "eth": ("#8c9bff", "#3a49c4", '<path d="M20 7.5 29 21l-9 5.2L11 21z" fill="#fff"/><path d="M20 28.4 29 23l-9 9.6L11 23z" fill="#fff" fill-opacity=".72"/>'),
    "bnb": ("#f3ba2f", "#a8770a", _t("BNB", 10.5, 24)),
    "sol": ("#9b6cff", "#0fb98f", '<path d="M11 12h18l-3 4.4H8zM8 17.8h18l3 4.4H11zM11 23.6h18l-3 4.4H8z" fill="#fff"/>'),
    "xrp": ("#5a6b86", "#1d2536", _t("X", 22)),
    "ada": ("#4f8df5", "#1a47a6", '<circle cx="20" cy="20" r="2.6" fill="#fff"/><circle cx="20" cy="11" r="1.9" fill="#fff"/><circle cx="20" cy="29" r="1.9" fill="#fff"/><circle cx="12.2" cy="15.5" r="1.9" fill="#fff"/><circle cx="27.8" cy="15.5" r="1.9" fill="#fff"/><circle cx="12.2" cy="24.5" r="1.9" fill="#fff"/><circle cx="27.8" cy="24.5" r="1.9" fill="#fff"/>'),
    "doge": ("#e7c25a", "#9a7415", _t("Ð", 24)),
    "ton": ("#3aa7f5", "#0b5eb0", '<path d="M10.5 12h19L20 30z" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/><path d="M20 12v18" stroke="#fff" stroke-width="2.2"/>'),
    "trx": ("#ef4f4f", "#a01818", '<path d="M10 12l20 3-10 16z" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/><path d="M10 12l11 7 9-4M21 19l-1 12" stroke="#fff" stroke-width="2" fill="none" stroke-linejoin="round"/>'),
    "ltc": ("#9fb0cc", "#40517a", _t("Ł", 24)),
    "bch": ("#46c47c", "#1b7a43", _t("₿", 24)),
    "dot": ("#ee2d8a", "#7a1148", '<circle cx="20" cy="12" r="3.2" fill="#fff"/><circle cx="20" cy="28" r="3.2" fill="#fff"/><circle cx="12" cy="16.5" r="3.2" fill="#fff"/><circle cx="28" cy="16.5" r="3.2" fill="#fff"/><circle cx="12" cy="23.5" r="3.2" fill="#fff"/><circle cx="28" cy="23.5" r="3.2" fill="#fff"/>'),
    "brent": ("#4b5262", "#10131a", _dropl("B", "#12151c")),
    "brent-spot": ("#5a6272", "#171b24", _dropl("B", "#12151c") + '<circle cx="29" cy="12" r="3" fill="#7ee0a8"/>'),
    "wti": ("#6a7484", "#1f242d", _dropl("W", "#1f242d")),
    "wti-spot": ("#778091", "#262c36", _dropl("W", "#1f242d") + '<circle cx="29" cy="12" r="3" fill="#7ee0a8"/>'),
    "opec-basket": ("#3d6a8c", "#0f2f49", _dropl("O", "#0f2f49")),
    "natural-gas": ("#4aa8ff", "#1450a8", '<path d="M20 6c1 5-6 8-6 15a6 6 0 0 0 12 0c0-3-1.6-4.6-3-6 .2 2.2-1 3.6-2.2 3.6C19.8 17 21.5 11.5 20 6z" fill="#fff"/>'),
}


def icon(id_, size=40):
    c1, c2, g = ICONS.get(id_, ("#3aa68a", "#12604f", _t("•", 22)))
    return (f'<span class="bni" aria-hidden="true" style="--a:{c1};--b:{c2};--s:{size}px">'
            f'<svg viewBox="0 0 40 40" fill="none">{g}</svg></span>')


ORDER = {
    "currency": ["usd", "eur", "gbp", "aed"],
    "gold": ["gold-18k", "gold-24k", "gold-mesghal", "coin-emami", "coin-bahar-azadi", "coin-half", "coin-quarter", "coin-gram",
             "xau", "paxg", "silver-999", "xag", "xpt", "xpd"],
    "crypto": ["btc", "usdt", "eth", "bnb", "sol", "xrp", "ada", "doge", "ton", "trx", "ltc", "bch", "dot"],
    "energy": ["brent", "brent-spot", "wti", "wti-spot", "opec-basket", "natural-gas"],
}
GROUP_TITLE = {"currency": "ارز", "gold": "طلا، سکه و فلزات گرانبها", "crypto": "ارز دیجیتال", "energy": "نفت و انرژی"}
CORE_IDS = ["usd", "eur", "gbp", "aed", "usdt", "gold-18k", "coin-emami", "coin-half", "coin-quarter", "xau", "btc", "eth", "brent", "wti"]


def asset_page(a):
    id_, name, h1, cat, unit, blurb = a
    extra = CONTENT[id_]
    title = f"{h1} | بازارنما"
    desc = f"{h1}؛ نرخ بازار {name} به {unit} همراه با تغییر 24 ساعته، زمان آخرین داده، منبع قیمت و راهنمای عوامل مؤثر در بازارنما."
    rel = "".join(f'<a href="/price-{o[0]}.html">{html.escape(o[1])}</a>' for o in A if o[3] == cat and o[0] != id_)
    others = "".join(f'<a href="/price-{o[0]}.html">{html.escape(o[1])}</a>' for o in A if o[3] != cat)
    faq = "".join(f'<article class="faq-item"><h3>{html.escape(q)}</h3><p>{html.escape(ans)}</p></article>' for q,ans in extra["faq"])
    body = f"""<section class="hero"><div class="eyebrow">بازارنما | {CATN[cat]}</div><h1 style="display:flex;align-items:center;gap:12px">{icon(id_, 48)}<span>{html.escape(h1)}</span></h1><p>{html.escape(blurb)}</p><div class="actions"><a class="btn" href="/prices.html">همه قیمت‌ها</a><a class="btn alt" href="/about.html">روش جمع‌آوری داده‌ها</a></div></section>
<section class="panel" aria-labelledby="live-title"><h2 id="live-title">نرخ لحظه‌ای {html.escape(name)}</h2><div class="kv"><div><small>قیمت</small><b id="price">…</b></div><div><small>واحد</small><b id="unit">{html.escape(unit)}</b></div><div><small>تغییر 24 ساعته</small><b id="chg">…</b></div><div><small>زمان داده</small><b id="time" style="font-size:15px">…</b></div></div><p><button class="smallbtn" type="button" id="shareBtn">اشتراک‌گذاری قیمت</button> <span id="shareMsg" class="muted" aria-live="polite"></span></p><p id="sourceInfo" class="muted" aria-live="polite">منبع و زمان آخرین به‌روزرسانی در حال دریافت…</p><p id="status" class="status" aria-live="polite">در حال دریافت اطلاعات…</p></section>
<section class="panel"><h2>نمودار تاریخی {html.escape(name)}</h2><p>نمودار، داده‌های تاریخی موجود برای این دارایی را نمایش می‌دهد؛ تعداد نقاط و بازه قابل مشاهده به تاریخچه‌ای بستگی دارد که منبع داده ارائه کرده است.</p><div class="toolbar" style="display:flex;flex-wrap:wrap;gap:7px;margin:10px 0"><button class="smallbtn active" type="button" data-range="7">7 روز</button><button class="smallbtn" type="button" data-range="30">30 روز</button><button class="smallbtn" type="button" data-range="90">3 ماه</button><button class="smallbtn" type="button" data-range="365">1 سال</button><button class="smallbtn" type="button" data-range="0">همه</button></div><canvas id="historyChart" aria-label="نمودار تاریخی قیمت {html.escape(name)}" style="display:block;width:100%;height:260px"></canvas><p id="chartHint" class="muted" aria-live="polite">در حال دریافت تاریخچه…</p></section>
<section class="panel" aria-labelledby="ret-title"><h2 id="ret-title">اگر در گذشته خریده بودی چه می‌شد؟</h2><p>مقدار دارایی را وارد کن (مثلاً 1 {html.escape(QTY.get(id_,"واحد"))}) تا ببینی در هر بازه چقدر پول داده بودی و الان ارزشش چقدر است. بر پایهٔ تاریخچهٔ ثبت‌شده در بازارنما است و پیش‌بینی یا توصیهٔ مالی نیست.</p><label for="retAmount">مقدار ({html.escape(QTY.get(id_,"واحد"))})</label> <input id="retAmount" type="number" inputmode="decimal" min="0" step="any" value="1" style="padding:7px 10px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);max-width:100%"><div class="kv" id="retGrid"><div><small>7 روز پیش</small><b data-ret="7">…</b></div><div><small>30 روز پیش</small><b data-ret="30">…</b></div><div><small>90 روز پیش</small><b data-ret="90">…</b></div><div><small>1 سال پیش</small><b data-ret="365">…</b></div></div><p id="retHint" class="muted" aria-live="polite"></p></section>
<section class="panel"><h2>درباره قیمت {html.escape(name)}</h2><p>{html.escape(extra['overview'])}</p><h3>چه عواملی بر قیمت اثر می‌گذارند؟</h3><p>{html.escape(extra['drivers'])}</p><h3>چطور این نرخ را بخوانیم؟</h3><p>{html.escape(extra['reading'])}</p></section>
<section class="panel"><h2>پرسش‌های متداول درباره {html.escape(name)}</h2>{faq}</section>
<section class="panel"><h2>قیمت‌های مرتبط</h2><div class="rel">{rel}</div><h3>سایر بازارها</h3><div class="rel">{others}</div><p>برای آشنایی با منبع داده، زمان به‌روزرسانی و محدودیت‌های نرخ‌ها، صفحه <a href="/about.html">درباره بازارنما و روش کار</a> را بخوان. قیمت‌های نمایش‌داده‌شده برای اطلاع‌رسانی هستند و توصیه خرید یا فروش محسوب نمی‌شوند.</p></section>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": f"{BASE}/price-{id_}.html#webpage", "name": title, "url": f"{BASE}/price-{id_}.html", "inLanguage": "fa-IR", "description": desc,
         "isPartOf": {"@type": "WebSite", "@id": BASE + "/#website", "name": "بازارنما", "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "بازارنما", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": CATN[cat], "item": BASE + CAT[cat] if CAT[cat].startswith("/") and not CAT[cat].startswith("/#") else BASE + "/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{BASE}/price-{id_}.html"}]},
        {"@type": "FAQPage", "@id": f"{BASE}/price-{id_}.html#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in extra["faq"]]}]}
    return page(title, desc, f"/price-{id_}.html", body, ld, ASSET_JS.replace("__ID__", json.dumps(id_)))


LIST_CSS = (".bni{display:inline-grid;place-items:center;width:var(--s,40px);height:var(--s,40px);flex:0 0 var(--s,40px);border-radius:50%;"
            "background:radial-gradient(circle at 30% 22%,rgba(255,255,255,.38),transparent 55%),linear-gradient(150deg,var(--a),var(--b));color:#fff;"
            "box-shadow:0 5px 12px color-mix(in srgb,var(--b) 33%,transparent),inset 0 1px 0 #ffffff66}.bni svg{width:62%;height:62%;display:block}"
            ".plist{display:grid;gap:8px;margin-top:12px}.prow{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;padding:10px 14px;border:1px solid var(--line);"
            "border-radius:14px;background:var(--surface);text-decoration:none;color:var(--text)}.prow:hover{border-color:var(--brand,#087e6e)}.prow .pn{font-weight:700}"
            ".prow .pv{text-align:left;font-weight:800;font-size:18px}.prow small{display:block;color:var(--muted);font-weight:400;font-size:12px}.prow .pc{font-size:13px;font-weight:700}"
            ".pnav{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.pnav a{border:1px solid var(--line);border-radius:999px;padding:4px 14px;text-decoration:none;color:var(--text);background:var(--surface)}"
            "#q{margin-top:10px;width:100%;max-width:420px;padding:9px 12px;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--text)}")

LIST_JS = """const fmt=(v,d)=>new Intl.NumberFormat('fa-IR-u-nu-latn',{maximumFractionDigits:d??(v<10?4:v<1000?2:0)}).format(v);
const U={IRT:'تومان',USD:'دلار',USDT:'تتر'};
fetch('/data/prices.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
 const m=new Map((d.items||[]).map(i=>[i.id,i]));let n=0;
 document.querySelectorAll('[data-p]').forEach(el=>{const x=m.get(el.dataset.p);if(x&&typeof x.price==='number'){el.textContent=fmt(x.price);n++;
  const c=document.querySelector('[data-c="'+el.dataset.p+'"]');if(c&&typeof x.change_pct==='number'){c.textContent='\\u2066'+(x.change_pct>0?'+':'')+fmt(x.change_pct,2)+'٪\\u2069';c.className='pc '+(x.change_pct>0?'up':x.change_pct<0?'down':'');}}
  else el.textContent='ناموجود';});
 const st=document.getElementById('st'),t=d.fetched_utc||d.generated_utc;
 if(st&&t){const dt=new Date(t);st.textContent='آخرین به‌روزرسانی داده: '+dt.toLocaleString('fa-IR-u-nu-latn',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'}).replace(/[,،]\\s*/,' ساعت ');}
}).catch(()=>{document.querySelectorAll('[data-p]').forEach(el=>el.textContent='ناموجود');});
const q=document.getElementById('q');
if(q)q.addEventListener('input',()=>{const v=q.value.trim();document.querySelectorAll('.price').forEach(r=>{r.hidden=!!v&&!r.dataset.n.includes(v);});
 document.querySelectorAll('section[data-g]').forEach(s=>{s.hidden=!s.querySelector('.price:not([hidden])');});});"""


def list_page(path, title, h1, desc, cats):
    names = {a[0]: a for a in A}
    secs, nav = "", ""
    for c in cats:
        rows = ""
        for i in ORDER[c]:
            a = names[i]
            rows += (f'<article class="price" data-n="{html.escape(a[1])}"><strong>{icon(i, 38)}<a href="/price-{i}.html">{html.escape(a[1])}</a></strong>'
                     f'<b data-p="{i}">در حال دریافت…</b><small>واحد: {html.escape(a[4])} <span class="pc" data-c="{i}"></span></small></article>')
        secs += f'<section class="panel" id="g-{c}" data-g="{c}"><h2>{GROUP_TITLE[c]}</h2><div class="prices">{rows}</div></section>'
        nav += f'<a href="#g-{c}">{GROUP_TITLE[c]}</a>'
    nav_all = ""
    if len(cats) > 1:
        nav_all = f'<div class="pnav">{nav}</div>'
    body = (f'<section class="hero"><div class="eyebrow">بازارنما | لیست قیمت‌ها</div><h1>{html.escape(h1)}</h1><p>{html.escape(desc)}</p>'
            f'{nav_all}<input id="q" type="search" placeholder="جستجوی نام دارایی…" aria-label="جستجو"><p class="muted" id="st" aria-live="polite"></p></section>{secs}')
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": f"{BASE}{path}", "url": f"{BASE}{path}", "name": title, "description": desc, "inLanguage": "fa-IR",
         "isPartOf": {"@type": "WebSite", "name": "بازارنما", "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "بازارنما", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": h1, "item": f"{BASE}{path}"}]}]}
    return page(title, desc, path, body, ld, LIST_JS).replace("</style><style id=\"glass\">", LIST_CSS + "</style><style id=\"glass\">", 1)


def about():
    title = "درباره بازارنما و روش جمع‌آوری قیمت‌ها"
    desc = "بازارنما چیست، قیمت‌ها از کجا می‌آیند، هر چند وقت به‌روز می‌شوند و محدودیت‌های داده‌ها چیست."
    body = """<section class="hero"><div class="eyebrow">بازارنما</div><h1>درباره بازارنما و روش کار</h1><p>بازارنما نمای ساده و سریعی از قیمت ارز، طلا، سکه، رمزارز و نفت است.</p></section>
<section class="panel"><h2>قیمت‌ها از کجا می‌آیند؟</h2><p>قیمت‌ها از رابط داده <a href="https://nerkhara.com/en/api/" rel="noopener noreferrer">NerkhAra</a> گرفته می‌شوند که نرخ را از چند منبع گردآوری می‌کند. بازارنما خودش قیمت‌گذاری نمی‌کند؛ فقط نمایش می‌دهد.</p><p>وضعیت لحظه‌ای منابع، تازگی هر دارایی و محدودیت‌های داده در صفحهٔ <a href="/transparency.html">شفافیت و اعتبار داده‌ها</a> آمده است.</p><p>برای مقایسهٔ دارایی‌ها، نقشهٔ حرارتی و آمار نوسان تاریخی به صفحهٔ <a href="/analysis.html">تحلیل بازار</a> بروید.</p><p>ماشین‌حساب طلا و سود و زیان تاریخی در <a href="/tools.html">ابزارهای بازارنما</a> است.</p><p>راهنمای استفاده از داده‌ها در <a href="/api-docs.html">مستندات API</a> است.</p><p>برای دلار، یورو، پوند و درهم، بازارنما دادهٔ NerkhAra را با دادهٔ مستقل Iran Market Data بررسی می‌کند. نرخ مستقیم بازار آزاد برای یورو، پوند و درهم جایگزین تبدیل از دلار می‌شود؛ نرخ‌های دو منبع نیز از نظر اختلاف کنترل می‌شوند. Frankfurter فقط برای نرخ‌های مرجع جهانی و CoinGecko برای پشتیبان قیمت بیت‌کوین و اتریوم استفاده می‌شود، نه برای ساخت نرخ مستقل ارزهای بازار آزاد ایران.</p><h2>هر چند وقت به‌روز می‌شود؟</h2><p>فرایند خودکار GitHub Actions تقریباً هر 10 دقیقه داده‌ها را دریافت و ذخیره می‌کند؛ اجرای دقیق ممکن است گاهی دیرتر انجام شود. تاریخچهٔ روزانهٔ منبع و نقاط ساعتی بازارنما در مخزن نگه‌داری می‌شوند و با انتشارهای بعدی حذف نمی‌شوند. اگر منبع در دسترس نباشد، آخرین قیمت ذخیره‌شده با برچسب «قدیمی» نمایش داده می‌شود و به‌عنوان نرخ زنده معرفی نمی‌شود.</p><h2>زمان داده یعنی چه؟</h2><p>کنار هر قیمت، زمان انتشار داده توسط منبع و تعداد منابع نوشته می‌شود تا بتوانی تازگی عدد را بسنجی.</p><h2>اخبار</h2><p>فقط تیتر، نام منبع، تاریخ و پیوند خبرها از RSS رسانه‌های خبری نمایش داده می‌شود و متن کامل در وب‌سایت ناشر خوانده می‌شود.</p><h2>محدودیت‌ها و سلب مسئولیت</h2><p>قیمت‌ها برای آگاهی عمومی‌اند و تضمین‌کننده قیمت نهایی معامله نیستند. بازار آزاد ممکن است در لحظه با عدد نمایش‌داده‌شده تفاوت داشته باشد. اطلاعات این سایت توصیه سرمایه‌گذاری، خرید یا فروش نیست.</p><h2>کنترل کیفیت قیمت‌ها</h2><p>هر قیمت پیش از انتشار با بازهٔ ۲۴ ساعت گذشتهٔ خودِ بازارنما سنجیده می‌شود. اگر عددی ناگهان از محدودهٔ منطقی بیرون برود، تا تأیید دومین دریافت پشت‌سر‌هم منتشر نمی‌شود و آخرین قیمت معتبر با برچسب «قدیمی» می‌ماند؛ بنابراین یک جهش واقعی بازار با فاصلهٔ کوتاهی پذیرفته می‌شود و یک خطای لحظه‌ای وارد قیمت‌ها و نمودارها نمی‌شود. دلیل پذیرش یا نگه‌داشتن هر قیمت در فایل <a href="/data/validation-log.json">validation-log.json</a> ثبت می‌شود.</p><h2>منابع و شرایط استفاده از داده</h2><p>بازارنما مالک داده‌های منابع نام‌برده نیست و برای بازنشر تجاری آن‌ها مجوز رسمی ادعا نمی‌کند. شرایط استفادهٔ هر منبع هنوز یکی‌یکی بررسی نشده است؛ تا آن زمان قیمت‌ها فقط برای اطلاع‌رسانی عمومی نمایش داده می‌شوند.</p><h2>سیاست انتشار و اصلاح</h2><p>بازارنما قیمت و خبر تولید یا تفسیر نمی‌کند؛ اخبار با تیتر، نام رسانه و پیوند به منبع اصلی نمایش داده می‌شوند و فقط خبرهای مرتبط با اقتصاد و دارای تاریخ انتشار معتبر می‌مانند. خبر تکراری چند رسانه یک‌بار نمایش داده می‌شود. اگر خطایی در قیمت یا اطلاعات یک صفحه مشخص شود، پس از بررسی اصلاح می‌شود.</p><h2>هشدار قیمت</h2><p>هشدارهای قیمت در مرورگر خودت ذخیره می‌شوند و فقط وقتی کار می‌کنند که صفحه بازارنما باز باشد؛ اطلاعاتی از تو روی سرور ما نگه داشته نمی‌شود.</p></section>"""
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "name": title, "url": BASE + "/about.html", "inLanguage": "fa-IR", "description": desc}
    return page(title + " | بازارنما", desc, "/about.html", body, ld)


def main():
    for a in A:
        (ROOT / f"price-{a[0]}.html").write_text(finalize(asset_page(a)), encoding="utf-8")
    (ROOT / "about.html").write_text(finalize(about()), encoding="utf-8")
    (ROOT / "prices.html").write_text(finalize(list_page("/prices.html", "لیست قیمت‌ها | همه قیمت‌های بازارنما", "همهٔ قیمت‌ها",
        "قیمت لحظه‌ای ارز، طلا، سکه، نقره، فلزات گرانبها، نفت، گاز و ارزهای دیجیتال در یک صفحه؛ با دسترسی به صفحهٔ جداگانهٔ هر دارایی.",
        ["currency", "gold", "crypto", "energy"])), encoding="utf-8")
    (ROOT / "energy.html").write_text(finalize(list_page("/energy.html", "قیمت نفت و انرژی | برنت، WTI، سبد اوپک و گاز طبیعی", "قیمت نفت و انرژی",
        "قیمت نفت برنت، WTI، سبد نفتی اوپک و گاز طبیعی به دلار؛ با لینک به صفحهٔ جداگانهٔ هر مورد.", ["energy"])), encoding="utf-8")
    (ROOT / "bn-icons.js").write_text("window.BN_ICONS=" + json.dumps({k: icon(k, 44) for k in ICONS}, ensure_ascii=False) + ";\n", encoding="utf-8")
    # sitemap.xml is NOT rewritten here: it contains more pages than this script generates and its lastmod dates
    # must reflect real page changes. tools/update_sitemap.py does that (run it after this script).
    import subprocess, sys as _sys
    subprocess.run([_sys.executable, str(ROOT / "tools" / "update_sitemap.py")], check=True)
    import re as _re
    glass = '<style id="glass">' + GLASS + '</style>'
    for f in ROOT.glob("*.html"):
        t = f.read_text(encoding="utf-8")
        t2 = _re.sub(r'<style id="glass">.*?</style>', lambda m: glass, t, flags=_re.S)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    print("built", len(A), "asset pages")


if __name__ == "__main__":
    main()
