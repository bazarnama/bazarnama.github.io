#!/usr/bin/env python3
"""Build tools.html ("ابزارهای بازارنما"): gold calculator + historical profit/loss calculator.
Converter, favorites and price alerts already exist on the home page and are NOT duplicated (links only).
Rates come from /api/v1/latest.json; a stale/unknown rate blocks the gold calculation. Usage: python tools/build_tools.py
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shell import shell

TITLE = "ابزارهای بازارنما: ماشین‌حساب طلا و سود و زیان تاریخی | بازارنما"
DESC = "ماشین‌حساب طلا با عیار و وزن و ماشین‌حساب سود و زیان تاریخی بر پایهٔ نرخ و تاریخچهٔ واقعی بازارنما؛ ابزار محاسباتی است، نه توصیهٔ سرمایه‌گذاری."
CSS = """.f{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}.f label{display:block;color:var(--muted);font-size:14px}.f input,.f select{width:100%;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text)}
.out{margin-top:10px}.out table{border-collapse:collapse;width:100%}.out td{border-bottom:1px solid var(--line);padding:6px 4px}.out td:last-child{text-align:left;font-weight:700}.msg{color:var(--muted)}.warn{color:#c0392b}.fx{direction:ltr;unicode-bidi:embed;color:var(--muted);font-size:13px}"""
BODY = """<header class="top"><a class="brand" href="/">بازارنما</a><div class="top-actions"><a href="/">بازگشت به صفحه اصلی ←</a><button class="theme-toggle" id="themeBtn" type="button" aria-label="تغییر حالت شب و روز">☾</button></div></header>
<section class="hero"><div class="eyebrow">بازارنما</div><h1>ابزارهای بازارنما</h1><p>ابزارهای محاسباتی بر پایهٔ نرخ‌ها و تاریخچهٔ واقعی. هیچ‌کدام توصیهٔ خرید یا فروش نیستند.</p></section>
<section class="panel"><h2>ماشین‌حساب طلا</h2>
<div class="f"><div><label for="gBase">نرخ مبنا</label><select id="gBase"></select></div><div><label for="gKarat">عیار</label><select id="gKarat"></select></div><div><label for="gW">وزن</label><input id="gW" inputmode="decimal" autocomplete="off" placeholder="مثلاً 2.5"></div><div><label for="gU">واحد وزن</label><select id="gU"></select></div>
<div><label for="gWage">اجرت (٪ از ارزش خام)</label><input id="gWage" inputmode="decimal" value="0"></div><div><label for="gProfit">سود فروشنده (٪ از خام + اجرت)</label><input id="gProfit" inputmode="decimal" value="0"></div><div><label for="gTax">مالیات (٪ از اجرت + سود)</label><input id="gTax" inputmode="decimal" value="0"></div></div>
<p class="msg" id="gRate" role="status"></p><div class="out" id="gOut"></div><p class="fx" id="gFx"></p>
<p class="msg">اجرت، سود و مالیات فقط وقتی محاسبه می‌شوند که خودتان درصدشان را وارد کنید؛ پیش‌فرض ۰ است و بازارنما نرخی برای آن‌ها فرض نمی‌کند. «ارزش خام» همان قیمت طلا بدون این هزینه‌هاست.</p></section>
<section class="panel"><h2>ماشین‌حساب سود و زیان تاریخی</h2>
<div class="f"><div><label for="pAsset">دارایی</label><select id="pAsset"></select></div><div><label for="pQty">مقدار فرضی (واحد دارایی)</label><input id="pQty" inputmode="decimal" value="1"></div><div><label for="pBuy">تاریخ خرید</label><input id="pBuy" type="date"></div><div><label for="pSell">تاریخ فروش (خالی = آخرین نقطهٔ ثبت‌شده)</label><input id="pSell" type="date"></div></div>
<button class="btn" id="pGo" type="button">محاسبه</button><p class="msg" id="pMsg" role="status"></p><div class="out" id="pOut"></div>
<p class="msg">قیمت هر تاریخ، نزدیک‌ترین نقطهٔ ثبت‌شده در ۷ روز پیش از آن است؛ اگر نقطه‌ای نباشد، «داده کافی نیست» نمایش داده می‌شود. نتیجه فقط محاسبهٔ گذشته است و نه پیش‌بینی یا توصیهٔ سرمایه‌گذاری؛ کارمزد و مالیات در آن لحاظ نشده است.</p></section>
<section class="panel"><h2>ابزارهای دیگر</h2><p>تبدیل‌گر ارز، علاقه‌مندی‌ها و هشدار قیمت در <a href="/">صفحهٔ اصلی</a> هستند. برای مقایسهٔ دارایی‌ها به <a href="/analysis.html">تحلیل بازار</a> بروید.</p></section>
<footer class="footer"><a href="/">صفحه اصلی بازارنما</a> · <a href="/prices.html">همه قیمت‌ها</a> · <a href="/analysis.html">تحلیل بازار</a> · <a href="/transparency.html">شفافیت و اعتبار داده‌ها</a> · <a href="/tools.html">ابزارهای بازارنما</a> · <a href="/about.html">درباره بازارنما و روش کار</a></footer>
</main>"""
JS = r"""<script>
/*CALC*/
const GRAM={gram:1,mesghal:4.6083,ounce:31.1035,kg:1000};
function num(s){if(s==null)return NaN;const t=String(s).trim().replace(/[,٬\s]/g,'').replace(/٫/g,'.');return t===''||!/^\d*\.?\d+$/.test(t)?NaN:Number(t)}
function gold(o){const w=num(o.weight),k=o.karat,bk=o.baseKarat,p=o.price,u=GRAM[o.unit];if(!(w>0)||!(p>0)||!u||!(k>0&&k<=24)||!(bk>0))return null;
const wg=num(o.wagePct||'0'),pf=num(o.profitPct||'0'),tx=num(o.taxPct||'0');if([wg,pf,tx].some(x=>isNaN(x)||x<0||x>100))return null;
const grams=w*u,raw=grams*(k/bk)*p,wage=raw*wg/100,profit=(raw+wage)*pf/100,tax=(wage+profit)*tx/100;return{grams,raw,wage,profit,tax,total:raw+wage+profit+tax}}
function onOrBefore(pts,ts,maxDays){let lo=0,hi=pts.length-1,r=-1;while(lo<=hi){const m=(lo+hi)>>1;if(pts[m].timestamp<=ts){r=m;lo=m+1}else hi=m-1}if(r<0||ts-pts[r].timestamp>maxDays*86400)return null;return pts[r]}
function pnl(qty,buy,sell){if(!(qty>0)||!buy||!sell||!(buy.price>0))return null;const b=qty*buy.price,s=qty*sell.price;return{buy:b,sell:s,diff:s-b,pct:(s/b-1)*100}}
if(typeof module!=='undefined')module.exports={num,gold,onOrBefore,pnl};
/*END*/
(()=>{if(typeof document==='undefined')return;
const $=id=>document.getElementById(id),fmt=(x,d=0)=>isFinite(x)?x.toLocaleString('en-US',{maximumFractionDigits:d}):'نامشخص';
const el=(t,x,c)=>{const e=document.createElement(t);if(x!=null)e.textContent=x;if(c)e.className=c;return e};
const opt=(s,v,t)=>{const o=el('option',t);o.value=v;s.append(o)};let items=[];const cache={};
const U=[['gram','گرم'],['mesghal','مثقال (۴٫۶۰۸۳ گرم)'],['ounce','اونس تروی (۳۱٫۱۰۳۵ گرم)'],['kg','کیلوگرم']];
for(const [v,t] of U)opt($('gU'),v,t);for(const k of [24,22,21,20,18,14,10,9])opt($('gKarat'),k,k+' عیار');$('gKarat').value='18';
const BASES=[['gold-18k',18],['gold-24k',24]];
function row(t,v){const r=el('tr');r.append(el('td',t),el('td',v));return r}
function calc(){const b=BASES.find(x=>x[0]===$('gBase').value),it=items.find(i=>i.id===$('gBase').value),out=$('gOut');out.textContent='';$('gFx').textContent='';
if(!it){$('gRate').textContent='نرخ در دسترس نیست.';return}const st=(it.freshness||{}).status;
$('gRate').textContent='نرخ مبنا: '+fmt(it.price)+' تومان به ازای هر گرم '+b[1]+' عیار · زمان نرخ: '+(it.updated_utc||'نامشخص')+' · وضعیت: '+({fresh:'به‌روز',aging:'در آستانهٔ تأخیر'}[st]||'قدیمی یا نامشخص');
if(st!=='fresh'&&st!=='aging'){out.append(el('p','نرخ مبنا به‌روز نیست؛ محاسبه انجام نمی‌شود.','warn'));return}
const r=gold({weight:$('gW').value,karat:Number($('gKarat').value),baseKarat:b[1],price:it.price,unit:$('gU').value,wagePct:$('gWage').value,profitPct:$('gProfit').value,taxPct:$('gTax').value});
if(!r){out.append(el('p','ورودی‌ها را بررسی کنید (وزن مثبت؛ درصدها بین ۰ و ۱۰۰).','msg'));return}
if(st==='aging')out.append(el('p','هشدار: نرخ در آستانهٔ تأخیر است.','warn'));
const t=el('table');[['وزن به گرم',fmt(r.grams,4)],['ارزش خام (تومان)',fmt(r.raw)],['اجرت',fmt(r.wage)],['سود فروشنده',fmt(r.profit)],['مالیات',fmt(r.tax)],['جمع کل (تومان)',fmt(r.total)]].forEach(x=>t.append(row(x[0],x[1])));out.append(t);
$('gFx').textContent='raw = grams × (karat / '+b[1]+') × rate ; wage = raw×w ; profit = (raw+wage)×p ; tax = (wage+profit)×t'}
for(const [id,k] of BASES)opt($('gBase'),id,'طلای '+k+' عیار (تومان/گرم)');
['gBase','gKarat','gW','gU','gWage','gProfit','gTax'].forEach(i=>{$(i).addEventListener('input',calc);$(i).addEventListener('change',calc)});
async function J(u){const r=await fetch(u,{cache:'no-cache'});if(!r.ok)throw new Error(r.status);return r.json()}
async function hist(id){if(!cache[id])cache[id]=J('/api/v1/history/'+encodeURIComponent(id)+'.json').then(d=>d.points||[]).catch(()=>null);return cache[id]}
async function go(){const m=$('pMsg'),o=$('pOut');o.textContent='';m.textContent='';const id=$('pAsset').value,q=num($('pQty').value),pts=await hist(id);
if(!pts||!pts.length){m.textContent='تاریخچه در دسترس نیست.';return}if(!(q>0)){m.textContent='مقدار باید عدد مثبت باشد.';return}if(!$('pBuy').value){m.textContent='تاریخ خرید را وارد کنید.';return}
const bt=Date.parse($('pBuy').value+'T00:00:00Z')/1000,st=$('pSell').value?Date.parse($('pSell').value+'T23:59:59Z')/1000:pts[pts.length-1].timestamp;
if(st<bt){m.textContent='تاریخ فروش باید بعد از خرید باشد.';return}
const b=onOrBefore(pts,bt,7),s=onOrBefore(pts,st,7),r=pnl(q,b,s);if(!r){m.textContent='داده کافی نیست: برای یکی از دو تاریخ نقطه‌ای در ۷ روز قبل ثبت نشده است.';return}
const d=ts=>new Date(ts*1000).toISOString().slice(0,10),u=(items.find(i=>i.id===id)||{}).unit||'';
const t=el('table');[['قیمت خرید ('+d(b.timestamp)+')',fmt(b.price,2)+' '+u],['قیمت فروش ('+d(s.timestamp)+')',fmt(s.price,2)+' '+u],['ارزش خرید',fmt(r.buy,2)],['ارزش فروش',fmt(r.sell,2)],['سود/زیان',(r.diff>0?'+':'')+fmt(r.diff,2)],['درصد تغییر',(r.pct>0?'+':'')+fmt(r.pct,2)+'٪']].forEach(x=>t.append(row(x[0],x[1])));o.append(t)}
$('pGo').onclick=go;
(async()=>{try{const L=await J('/api/v1/latest.json');items=(L.items||[]).filter(i=>i&&i.id);for(const i of items)opt($('pAsset'),i.id,((i.name||{}).fa||i.id)+' ('+i.unit+')');$('pAsset').value='gold-18k'}catch(e){$('gRate').textContent='دریافت نرخ ممکن نشد.'}calc()})();
})();
</script>"""

if __name__ == "__main__":
    shell("tools.html", TITLE, DESC, "WebPage", "ابزارهای بازارنما", BODY, CSS, JS)
    print("tools.html written")
