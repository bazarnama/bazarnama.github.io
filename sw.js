const V='bazarnama-v44',SHELL=['/','/prices.html','/currency.html','/gold.html','/crypto.html','/energy.html','/about.html','/transparency.html','/analysis.html','/tools.html','/api-docs.html','/bn-icons.js'];
// Pre-cache only the pages. Missing files must never break installation, so each is added on its own.
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>Promise.allSettled(SHELL.map(u=>c.add(u)))).catch(()=>{}));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
 const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);if(u.origin!==location.origin)return;
 // network first (prices/news must be fresh), cache as offline fallback
 // data/ and api/ files must never come from the HTTP cache (GitHub Pages sends max-age=600)
 const live=/^\/(data|api)\//.test(u.pathname);
 e.respondWith(fetch(live?new Request(r,{cache:'no-store'}):r).then(res=>{if(res.ok){const c=res.clone();caches.open(V).then(x=>x.put(r,c));}return res;}).catch(()=>caches.match(r).then(m=>m||caches.match('/'))));
});
