// Bazarnama live price relay (Cloudflare Worker).
// GET /live.json -> NerkhAra latest prices in the same format as /api/v1/latest.json, with per-item
// freshness added. The answer is cached at the edge for 60 s, so many visitors cause one upstream request
// per minute. It never invents or converts prices; dollar-derived items are dropped. If the upstream is
// down it answers 502 and the site falls back to its own data files.
const UPSTREAM = "https://nerkhara.com/api/v1/latest.json";
const CACHE_SECONDS = 60;
const LIMITS = { crypto: 1200, currency: 5400, gold: 7200, coin: 7200, metal: 7200, energy: 7200 };
const DEFAULT_LIMIT = 4 * 3600;
const DAILY = new Set(["brent-spot", "wti-spot", "opec-basket", "natural-gas"]);

function toIso(v) {
  if (!v) return null;
  const s = String(v);
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + "Z");
  return isNaN(d) ? null : d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function normalize(upstream, now = Date.now()) {
  const items = [];
  for (const it of Array.isArray(upstream && upstream.items) ? upstream.items : []) {
    if (!it || !it.id || it.derived === true) continue;
    if (typeof it.price !== "number" || !isFinite(it.price) || it.price <= 0) continue;
    const observed = toIso(it.updated_utc || it.as_of);
    const limit = DAILY.has(it.id) ? 4 * 86400 : (LIMITS[String(it.family || "").toLowerCase()] || DEFAULT_LIMIT);
    let status = "unknown", age = null;
    if (observed) {
      age = Math.max(0, Math.floor((now - Date.parse(observed)) / 1000));
      status = age > limit ? "stale" : age > limit * 0.65 ? "aging" : "fresh";
    }
    const row = { ...it, source_name: "NerkhAra", live_via: "cloudflare-worker",
      freshness: { status, observed_utc: observed, age_seconds: age, max_age_seconds: limit, clock_basis: observed ? "provider_timestamp" : "unknown" } };
    if (status === "stale") row.stale = true;
    items.push(row);
  }
  return { api: "bazarnama-live/v1", generated_utc: new Date(now).toISOString().replace(/\.\d{3}Z$/, "Z"),
           fetched_utc: new Date(now).toISOString().replace(/\.\d{3}Z$/, "Z"), items };
}

function corsHeaders(request, env) {
  const allowed = String((env && env.ALLOWED_ORIGINS) || "https://bazarnama.github.io").split(",").map(s => s.trim()).filter(Boolean);
  const origin = request.headers.get("Origin");
  return { "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0], "Vary": "Origin",
           "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "Accept" };
}

function reply(body, status, extra, request, env) {
  return new Response(body, { status, headers: { "content-type": "application/json; charset=utf-8", ...extra, ...corsHeaders(request, env) } });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return reply(null, 204, {}, request, env);
    if (request.method !== "GET") return reply('{"error":"method_not_allowed"}', 405, {}, request, env);
    const path = new URL(request.url).pathname;
    if (path !== "/live.json" && path !== "/") return reply('{"error":"not_found"}', 404, {}, request, env);
    const cache = caches.default;
    const key = new Request("https://bazarnama-live.invalid/live.json");
    const hit = await cache.match(key);
    if (hit) return reply(await hit.text(), 200, { "cache-control": `public, max-age=${CACHE_SECONDS}`, "x-cache": "HIT" }, request, env);
    try {
      const r = await fetch(UPSTREAM, { headers: { Accept: "application/json", "User-Agent": "bazarnama-live" }, cf: { cacheTtl: 0 } });
      if (!r.ok) throw new Error("upstream " + r.status);
      const out = normalize(await r.json());
      if (!out.items.length) throw new Error("no valid items");
      const text = JSON.stringify(out);
      ctx.waitUntil(cache.put(key, new Response(text, { headers: { "cache-control": `public, max-age=${CACHE_SECONDS}` } })));
      return reply(text, 200, { "cache-control": `public, max-age=${CACHE_SECONDS}`, "x-cache": "MISS" }, request, env);
    } catch (e) {
      return reply('{"error":"upstream_unavailable"}', 502, { "cache-control": "no-store" }, request, env);
    }
  },
};
