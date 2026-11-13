import assert from "node:assert/strict";
import worker, { normalize } from "./worker.js";

const now = Date.parse("2026-11-13T18:30:00Z");
const up = { items: [
  { id: "usd", family: "currency", price: 268650, updated_utc: "2026-11-13T18:14:43" },
  { id: "eur", family: "currency", price: 1, derived: true },
  { id: "btc", family: "crypto", price: 70000, updated_utc: "2026-11-13T17:00:00" },
  { id: "bad", family: "gold", price: -1 },
  { id: "brent-spot", family: "energy", price: 90, updated_utc: "2026-11-10T00:00:00" },
]};
const out = normalize(up, now);
assert.deepEqual(out.items.map(i => i.id), ["usd", "btc", "brent-spot"]);
assert.equal(out.items[0].freshness.status, "fresh");
assert.equal(out.items[1].freshness.status, "stale");
assert.equal(out.items[1].stale, true);
assert.notEqual(out.items[2].freshness.status, "stale");   // daily series: 3.8 days old is still allowed

const store = new Map();
globalThis.caches = { default: { match: async k => store.get(k.url)?.clone(), put: async (k, r) => { store.set(k.url, r); } } };
let calls = 0;
globalThis.fetch = async () => { calls++; return new Response(JSON.stringify(up), { status: 200 }); };
const ctx = { waitUntil: p => p };
const req = (m = "GET", p = "/live.json", o = "https://bazarnama.github.io") => new Request("https://w.example" + p, { method: m, headers: { Origin: o } });
let r = await worker.fetch(req(), {}, ctx);
assert.equal(r.status, 200); assert.equal(r.headers.get("x-cache"), "MISS");
assert.equal(r.headers.get("access-control-allow-origin"), "https://bazarnama.github.io");
r = await worker.fetch(req(), {}, ctx);
assert.equal(r.headers.get("x-cache"), "HIT"); assert.equal(calls, 1);
r = await worker.fetch(req("GET", "/live.json", "https://evil.example"), {}, ctx);
assert.equal(r.headers.get("access-control-allow-origin"), "https://bazarnama.github.io");
assert.equal((await worker.fetch(req("POST"), {}, ctx)).status, 405);
assert.equal((await worker.fetch(req("GET", "/x"), {}, ctx)).status, 404);
store.clear(); globalThis.fetch = async () => new Response("x", { status: 500 });
assert.equal((await worker.fetch(req(), {}, ctx)).status, 502);
console.log("worker tests ok");
