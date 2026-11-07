#!/usr/bin/env python3
"""Fetch prices from several sources and save them as static JSON for the site.

Files written (all optional for the browser — it falls back to live APIs):
  data/prices.json   latest prices + global FX cross rates (+ backup crypto prices)
  data/history.json  hourly price history built by this script (one point per hour)
  data/summary.json  short automatic market summary

Sources
  1) NerkhAra latest.json          - Iranian market prices (primary)
  2) Frankfurter (ECB)             - global FX cross rates per 1 USD (used for pound, euro,
                                     lira, yuan ... when the market feed has no value)
  3) CoinGecko (public endpoint)   - backup BTC / ETH / USDT prices in USD
  4) Stooq CSV (no key)            - delayed futures prices for Brent / WTI / natural gas
  5) EIA Open Data (US gov, needs a free key in env EIA_API_KEY) - external reference for
     Brent, WTI and Henry Hub natural gas (daily); also fills them when the primary feed lacks them
If the primary source is down the previous prices are kept and flagged stale.
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime, pathlib

PRIMARY = "https://nerkhara.com/api/v1/latest.json"
FX_URLS = [
    "https://api.frankfurter.dev/v1/latest?base=USD",
    "https://api.frankfurter.app/latest?from=USD",
]
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether"
             "&vs_currencies=usd&include_24hr_change=true")
CG_IDS = {"bitcoin": "btc", "ethereum": "eth", "tether": "usdt_usd"}

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "prices.json"
HIST = ROOT / "data" / "history.json"
SUMMARY = ROOT / "data" / "summary.json"
HIST_MAX = 24 * 14  # keep 14 days of hourly points

NAMES = {
    "usd": "دلار آمریکا", "eur": "یورو", "gbp": "پوند انگلیس", "aed": "درهم امارات", "usdt": "تتر",
    "gold-18k": "طلای 18 عیار", "coin-emami": "سکه امامی", "coin-half": "نیم‌سکه",
    "coin-quarter": "ربع‌سکه", "xau": "اونس جهانی طلا", "btc": "بیت‌کوین",
    "eth": "اتریوم", "natgas": "گاز طبیعی", "brent": "نفت برنت", "wti": "نفت WTI",
}


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "bazarnama-updater"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_primary(p):
    return isinstance(p, dict) and isinstance(p.get("items"), list) and any(
        isinstance(i, dict) and isinstance(i.get("price"), (int, float)) for i in p["items"])


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def fetch_fx():
    """Return ({CODE: units per 1 USD}, date) or (None, None)."""
    for url in FX_URLS:
        try:
            d = get_json(url)
            rates = d.get("rates")
            if isinstance(rates, dict) and rates:
                clean = {k: float(v) for k, v in rates.items() if isinstance(v, (int, float)) and v > 0}
                clean["USD"] = 1.0
                return clean, d.get("date")
        except Exception as e:  # noqa: BLE001
            print("fx source failed:", url, e, file=sys.stderr)
    return None, None


def fetch_coingecko():
    try:
        d = get_json(COINGECKO)
    except Exception as e:  # noqa: BLE001
        print("coingecko failed:", e, file=sys.stderr)
        return {}
    out = {}
    for cg, key in CG_IDS.items():
        row = d.get(cg) if isinstance(d, dict) else None
        if isinstance(row, dict) and isinstance(row.get("usd"), (int, float)):
            out[key] = {"price": float(row["usd"]), "change_pct": row.get("usd_24h_change")}
    return out


EIA_SERIES = [  # (id, route, series code, unit)
    ("brent", "petroleum/pri/spt", "RBRTE", "USD"),
    ("wti", "petroleum/pri/spt", "RWTC", "USD"),
    ("natgas", "natural-gas/pri/fut", "RNGWHHD", "USD"),
]


STOOQ_SYMBOLS = {  # id -> candidate symbols (first plausible one wins), plausible price range
    "brent": (["cb.f", "lco.f"], 10, 400),
    "wti": (["cl.f"], 10, 400),
    "natgas": (["ng.f"], 0.5, 40),
}


def fetch_stooq():
    """Delayed futures prices (a few minutes to ~20 min late) from Stooq CSV. No key needed."""
    out = {}
    for pid, (symbols, lo, hi) in STOOQ_SYMBOLS.items():
        for sym in symbols:
            try:
                req = urllib.request.Request(f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv",
                                             headers={"User-Agent": "bazarnama-updater"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    lines = r.read().decode("utf-8", "replace").strip().splitlines()
                if len(lines) < 2:
                    continue
                head = [h.strip().lower() for h in lines[0].split(",")]
                row = dict(zip(head, [c.strip() for c in lines[1].split(",")]))
                price = float(row["close"])
                if not (lo <= price <= hi):
                    continue
                out[pid] = {"price": price, "unit": "USD", "date": row.get("date"), "time": row.get("time"),
                            "symbol": sym, "source": "Stooq"}
                break
            except Exception as e:  # noqa: BLE001
                print("Stooq failed for", pid, sym, type(e).__name__, file=sys.stderr)
    return out


def fetch_eia():
    """Daily Brent / WTI / Henry Hub from the US EIA. Returns {id: {...}} (empty without a key)."""
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        print("EIA_API_KEY not set; skipping EIA.")
        return {}
    out = {}
    for pid, route, code, unit in EIA_SERIES:
        q = urllib.parse.urlencode([
            ("api_key", key), ("frequency", "daily"), ("data[0]", "value"), ("facets[series][]", code),
            ("sort[0][column]", "period"), ("sort[0][direction]", "desc"), ("length", "5")])
        try:
            rows = get_json(f"https://api.eia.gov/v2/{route}/data/?{q}")["response"]["data"]
            vals = [(r["period"], float(r["value"])) for r in rows if r.get("value") not in (None, "")]
            if vals:
                chg = (vals[0][1] - vals[1][1]) / vals[1][1] * 100 if len(vals) > 1 and vals[1][1] else None
                out[pid] = {"price": vals[0][1], "unit": unit, "date": vals[0][0], "change_pct": chg, "source": "EIA"}
        except Exception as e:  # noqa: BLE001  (never print the URL: it contains the key)
            print("EIA failed for", pid, type(e).__name__, file=sys.stderr)
    return out


def build_summary(payload):
    rows = []
    for i in payload["items"]:
        if i.get("id") in NAMES and isinstance(i.get("price"), (int, float)) and isinstance(i.get("change_pct"), (int, float)) and not i.get("stale"):
            rows.append((NAMES[i["id"]], i["change_pct"]))
    if not rows:
        return None
    rows.sort(key=lambda r: r[1])
    up = [r for r in rows if r[1] > 0]
    down = [r for r in rows if r[1] < 0]
    lines = []
    if up:
        lines.append(f"بیشترین افزایش ۲۴ ساعت گذشته: {up[-1][0]} با {abs(up[-1][1]):.2f}٪.")
    if down:
        lines.append(f"بیشترین کاهش ۲۴ ساعت گذشته: {down[0][0]} با {abs(down[0][1]):.2f}٪.")
    lines.append(f"از {len(rows)} دارایی دارای تغییر معتبر، {len(up)} مورد مثبت و {len(down)} مورد منفی‌اند.")
    return {"generated_utc": payload.get("generated_utc"), "lines": lines}


def update_history(items):
    data = load_json(HIST)
    series = data.get("series", {}) if isinstance(data, dict) else {}
    hour = int(time.time()) // 3600 * 3600
    for i in items:
        pid, price = i.get("id"), i.get("price")
        if not pid or not isinstance(price, (int, float)) or i.get("stale"):
            continue
        s = series.setdefault(pid, [])
        if s and s[-1][0] >= hour:
            continue
        s.append([hour, price])
        if len(s) > HIST_MAX:
            del s[: len(s) - HIST_MAX]
    HIST.write_text(json.dumps({"v": 1, "series": series}, separators=(",", ":")), encoding="utf-8")


def main():
    try:
        primary = get_json(PRIMARY)
        if not valid_primary(primary):
            primary = None
    except Exception as e:  # noqa: BLE001
        print("primary failed:", e, file=sys.stderr)
        primary = None

    fx, fx_date = fetch_fx()
    cg = fetch_coingecko()
    eia = fetch_eia()
    stooq = fetch_stooq()

    if primary:
        payload = primary
        payload["primary_ok"] = True
    else:
        prev = load_json(OUT)
        if not valid_primary(prev):
            if not fx and not cg:
                print("No valid data at all; keeping previous files.")
                return 0
            prev = {"items": []}
        payload = prev
        payload["primary_ok"] = False
        for i in payload["items"]:
            i["stale"] = True

    items = payload["items"]
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}

    # backup crypto prices (USD) when the primary feed does not have them
    for key in ("btc", "eth"):
        if key in cg and (key not in by_id or by_id[key].get("stale") or not isinstance(by_id[key].get("price"), (int, float))):
            row = {"id": key, "price": cg[key]["price"], "unit": "USD",
                   "change_pct": cg[key].get("change_pct"), "updated_utc": now_iso(),
                   "sources": 1, "backup_source": "coingecko"}
            if key in by_id:
                items[items.index(by_id[key])] = row
            else:
                items.append(row)
    if "usdt_usd" in cg:
        payload["usdt_usd"] = cg["usdt_usd"]["price"]  # USDT in USD (for reference)

    # energy: Stooq (delayed, fresher) and EIA (daily) are shown as references; they also
    # fill the value when the primary feed has none (Stooq first, then EIA).
    if eia:
        payload["external_energy"] = eia
    if stooq:
        payload["delayed_energy"] = stooq
    for pid in ("brent", "wti", "natgas"):
        cur = by_id.get(pid)
        has = cur and isinstance(cur.get("price"), (int, float)) and not cur.get("stale")
        if has:
            continue
        if pid in stooq:
            e = stooq[pid]
            row = {"id": pid, "price": e["price"], "unit": e["unit"], "change_pct": None,
                   "updated_utc": now_iso(), "sources": 1, "backup_source": "stooq", "delayed": True}
        elif pid in eia:
            e = eia[pid]
            row = {"id": pid, "price": e["price"], "unit": e["unit"], "change_pct": e["change_pct"],
                   "updated_utc": e["date"] + "T00:00:00Z", "sources": 1, "backup_source": "eia"}
        else:
            continue
        if cur:
            items[items.index(cur)] = row
        else:
            items.append(row)

    if fx:
        payload["fx_usd"] = fx
        payload["fx_date"] = fx_date

    # Fill currencies the market feed lacks from USD market price x global FX (flagged derived).
    usd = by_id.get("usd")
    if usd and isinstance(usd.get("price"), (int, float)) and not usd.get("stale") and fx:
        for pid, code in (("eur", "EUR"), ("gbp", "GBP"), ("aed", "AED")):
            cur = by_id.get(pid)
            has = cur and isinstance(cur.get("price"), (int, float)) and not cur.get("stale")
            per = fx.get(code) or (3.6725 if code == "AED" else None)
            if not has and per:
                row = {"id": pid, "price": round(usd["price"] / per), "unit": usd.get("unit", "IRT"),
                       "change_pct": None, "updated_utc": usd.get("updated_utc"), "sources": 0,
                       "derived": True, "derived_from": "usd x fx"}
                if cur:
                    items[items.index(cur)] = row
                else:
                    items.append(row)
    if usd and isinstance(usd.get("price"), (int, float)) and not usd.get("stale") and "usdt" not in {i.get("id") for i in items if isinstance(i.get("price"), (int, float))}:
        items.append({"id": "usdt", "price": usd["price"], "unit": usd.get("unit", "IRT"), "change_pct": usd.get("change_pct"),
                      "updated_utc": usd.get("updated_utc"), "sources": 0, "derived": True, "derived_from": "usd"})

    payload["source_status"] = {"primary": bool(primary), "fx": bool(fx), "coingecko": sorted(cg),
                                "stooq": sorted(stooq), "eia": sorted(eia), "eia_key_set": bool(os.environ.get("EIA_API_KEY", "").strip())}
    payload["fetched_utc"] = now_iso()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    update_history(items)
    s = build_summary(payload)
    if s:
        SUMMARY.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    print("Updated", OUT, "primary_ok =", payload["primary_ok"], "fx =", bool(fx), "coingecko =", sorted(cg), "stooq =", sorted(stooq), "eia =", sorted(eia))
    return 0


if __name__ == "__main__":
    sys.exit(main())
