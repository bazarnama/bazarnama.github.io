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
  4) Stooq CSV (no key)            - delayed futures prices for Brent / WTI
  5) EIA Open Data (US gov, needs a free key in env EIA_API_KEY) - external reference for
     Brent and WTI (daily); also fills them when the primary feed lacks them
If the primary source is down the previous prices are kept and flagged stale.
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime, pathlib, re, html
from zoneinfo import ZoneInfo

PRIMARY = "https://nerkhara.com/api/v1/latest.json"
SECONDARY_IRAN_MARKET = "https://raw.githubusercontent.com/iran-market/iran-market.github.io/main/data/popular.json"
DIRECT_CURRENCY_IDS = {"usd": "USD_IRR_FREE", "eur": "EUR_IRR_FREE", "gbp": "GBP_IRR_FREE", "aed": "AED_IRR_FREE"}
SITE_ASSETS = {"usd", "eur", "gbp", "aed", "usdt", "gold-18k", "coin-emami", "coin-half", "coin-quarter", "xau", "btc", "eth", "brent", "wti"}
FX_URLS = [
    "https://api.frankfurter.dev/v1/latest?base=USD",
    "https://api.frankfurter.app/latest?from=USD",
]
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether"
             "&vs_currencies=usd&include_24hr_change=true")
CG_IDS = {"bitcoin": "btc", "ethereum": "eth", "tether": "usdt_usd"}

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data" / "prices.json"
HIST = ROOT / "data" / "history.json"
SUMMARY = ROOT / "data" / "summary.json"
HIST_MAX = None  # preserve the full series; old points are never discarded

NAMES = {
    "usd": "دلار آمریکا", "eur": "یورو", "gbp": "پوند انگلیس", "aed": "درهم امارات", "usdt": "تتر",
    "gold-18k": "طلای 18 عیار", "coin-emami": "سکه امامی", "coin-half": "نیم‌سکه",
    "coin-quarter": "ربع‌سکه", "xau": "اونس جهانی طلا", "btc": "بیت‌کوین",
    "eth": "اتریوم", "brent": "نفت برنت", "wti": "نفت WTI",
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
]


STOOQ_SYMBOLS = {  # id -> candidate symbols (first plausible one wins), plausible price range
    "brent": (["cb.f", "lco.f"], 10, 400),
    "wti": (["cl.f"], 10, 400),
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



def parse_timestamp(value):
    """Parse ISO strings or Unix timestamps to epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 10**12 else float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def fetch_iran_market():
    """Independent direct Iranian free-market quotes for USD/EUR/GBP/AED."""
    try:
        payload = get_json(SECONDARY_IRAN_MARKET)
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("unexpected Iran Market Data response")
        result = {}
        for pid, symbol in DIRECT_CURRENCY_IDS.items():
            row = next((r for r in rows if isinstance(r, dict) and
                        str(r.get("symbol") or r.get("id") or "").upper() == symbol), None)
            if not row:
                continue
            try:
                price = float(row.get("price"))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            stamp_raw = row.get("updated_utc") or row.get("updated_at") or row.get("timestamp") or payload.get("generated_utc") or payload.get("updated_at")
            stamp = parse_timestamp(stamp_raw)
            if stamp is None:
                continue
            age = time.time() - stamp
            if age < -300 or age > 2 * 60 * 60:
                continue
            result[pid] = {
                "price": price, "unit": "IRT", "source_name": "Iran Market Data",
                "source_updated_utc": datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_checked_utc": now_iso(), "method": "direct", "stale": False,
            }
        return result
    except Exception as e:  # noqa: BLE001
        print("Iran Market Data failed:", type(e).__name__, file=sys.stderr)
        return {}



def jalali_to_gregorian(jy, jm, jd):
    """Convert a Jalali calendar date to a Gregorian date."""
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_days[gm - 1]:
        gd -= month_days[gm - 1]
        gm += 1
    return datetime.date(gy, gm, gd)


def fetch_arzhaam_aed():
    """Read the publicly displayed AED market quote and its source timestamp."""
    url = "https://arzhaam.ir/rates/aed"
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 (compatible; BazarnamaPriceBot/1.0)",
        })
        with urllib.request.urlopen(req, timeout=20) as response:
            page = response.read().decode("utf-8", "replace")
        page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
        visible = html.unescape(re.sub(r"<[^>]+>", " ", page))
        visible = re.sub(r"\s+", " ", visible)
        digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        visible = visible.translate(digits).replace("٬", ",").replace("٫", ".")

        # The first visible price is the current AED quote, in toman.
        price_match = re.search(r"([0-9][0-9,]*[0-9]|[0-9]+)\s*تومان", visible)
        time_match = re.search(
            r"آخرین\s*به[\u200c ]?روزرسانی\s*[:：]?\s*(\d{1,2})\s+([آ-ی]+)\s+(\d{4})[،, ]+\s*(\d{1,2}):(\d{2})",
            visible,
        )
        if not price_match or not time_match:
            raise ValueError("could not parse public AED price and timestamp")
        price = float(price_match.group(1).replace(",", ""))
        if not (1000 <= price <= 10_000_000):
            raise ValueError("AED price outside plausible bounds")

        months = {"فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5,
                  "شهریور": 6, "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10,
                  "بهمن": 11, "اسفند": 12}
        day, month_name, year, hour, minute = time_match.groups()
        if month_name not in months or int(hour) > 23:
            raise ValueError("invalid Jalali timestamp")
        gregorian = jalali_to_gregorian(int(year), months[month_name], int(day))
        tehran = datetime.datetime.combine(gregorian, datetime.time(int(hour), int(minute)), ZoneInfo("Asia/Tehran"))
        age = (datetime.datetime.now(ZoneInfo("Asia/Tehran")) - tehran).total_seconds()
        if age < -300 or age > 6 * 60 * 60:
            raise ValueError("Arzhaam AED quote is stale")

        return {"aed": {
            "price": price, "unit": "IRT", "source_name": "Arzhaam",
            "source_updated_utc": tehran.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_checked_utc": now_iso(), "method": "direct", "stale": False,
        }}
    except Exception as e:  # noqa: BLE001
        print("Arzhaam AED fallback failed:", type(e).__name__, file=sys.stderr)
        return {}

def select_currency_quotes(items, secondary):
    """Compare two independent quotes; reject derived EUR/GBP/AED values."""
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    checks = {}
    for pid in DIRECT_CURRENCY_IDS:
        primary = by_id.get(pid)
        alt = secondary.get(pid)
        p_ok = bool(primary and isinstance(primary.get("price"), (int, float)) and
                    not primary.get("stale") and primary.get("method") != "derived" and
                    not primary.get("derived"))
        a_ok = bool(alt and isinstance(alt.get("price"), (int, float)))
        discrepancy = None
        if p_ok and a_ok and primary.get("price"):
            discrepancy = abs(float(primary["price"]) - float(alt["price"])) / float(primary["price"]) * 100
        checks[pid] = {
            "primary_available": p_ok, "secondary_available": a_ok,
            "discrepancy_pct": round(discrepancy, 3) if discrepancy is not None else None,
            "threshold_pct": 5.0,
        }
        # Direct independent quote is preferred over a derived cross-rate.
        if a_ok and (not p_ok):
            chosen = dict(alt)
            chosen.update({"id": pid, "change_pct": None,
                           "updated_utc": chosen.get("source_updated_utc"),
                           "sources": 1,
                           "backup_source": str(chosen.get("source_name", "Iran Market Data")).lower().replace(" ", "-"),
                           "source_selection": "secondary-direct"})
            if primary:
                items[items.index(primary)] = chosen
            else:
                items.append(chosen)
            by_id[pid] = chosen
        elif p_ok:
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
            primary["source_updated_utc"] = primary.get("source_updated_utc") or primary.get("updated_utc") or primary.get("as_of")
            primary["source_checked_utc"] = now_iso()
            primary["source_selection"] = "primary-aggregated"
            if a_ok:
                primary["secondary_source"] = alt.get("source_name", "Iran Market Data")
                primary["secondary_price"] = alt["price"]
                primary["source_discrepancy_pct"] = checks[pid]["discrepancy_pct"]
                # Large disagreement is retained as a quality flag; don't silently average markets.
                primary["discrepancy_warning"] = discrepancy is not None and discrepancy > 5.0
        elif primary and pid in ("eur", "gbp", "aed") and (primary.get("method") == "derived" or primary.get("derived")):
            # Never publish a dollar-cross calculation as a direct Iranian free-market quote.
            items.remove(primary)
        elif primary:
            primary["stale"] = True
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
            primary["source_updated_utc"] = primary.get("updated_utc") or primary.get("as_of")
    return checks


def normalize_history(payload):
    """Accept common public JSON history shapes and return sorted [epoch, price] points."""
    rows = None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("data", "history", "points", "items", "rates", "series"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if rows is None and isinstance(payload.get("data"), dict):
            rows = payload["data"].get("points") or payload["data"].get("history")
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        stamp = price = None
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            stamp, price = row[0], row[1]
        elif isinstance(row, dict):
            stamp = row.get("timestamp") or row.get("time") or row.get("date") or row.get("day")
            price = row.get("price") or row.get("value") or row.get("close") or row.get("rate")
        ts = parse_timestamp(stamp)
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue
        if ts is not None and value > 0:
            out.append([int(ts), value])
    return sorted({p[0]: p for p in out}.values(), key=lambda p: p[0])


def seed_history(series, ids, seeded, attempts):
    """Import long-term daily history once per symbol; retry failed imports every six hours."""
    now = time.time()
    for pid in ids:
        if pid in seeded:
            continue
        last_try = parse_timestamp(attempts.get(pid))
        if last_try is not None and now - last_try < 6 * 60 * 60:
            continue
        attempts[pid] = now_iso()
        try:
            payload = get_json(f"https://nerkhara.com/api/v1/history/{urllib.parse.quote(pid)}.json")
            imported = normalize_history(payload)
            if imported:
                merged = {int(p[0]): [int(p[0]), float(p[1])] for p in series.get(pid, [])}
                merged.update({int(p[0]): [int(p[0]), float(p[1])] for p in imported})
                series[pid] = sorted(merged.values(), key=lambda p: p[0])
                seeded.add(pid)
                print("Seeded history", pid, len(imported))
        except Exception as e:  # noqa: BLE001
            print("History seed failed for", pid, type(e).__name__, file=sys.stderr)


def write_api_files(payload, history):
    api = ROOT / "api" / "v1"
    (api / "history").mkdir(parents=True, exist_ok=True)
    latest = {"api": "bazarnama/v1", "generated_utc": payload.get("generated_utc"),
              "fetched_utc": payload.get("fetched_utc"), "items": payload.get("items", [])}
    (api / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (api / "index.json").write_text(json.dumps({
        "api": "bazarnama/v1",
        "latest": "/api/v1/latest.json",
        "history_pattern": "/api/v1/history/{asset_id}.json",
        "assets": sorted(set([x.get("id") for x in payload.get("items", []) if x.get("id")])),
        "history_assets": sorted(history.get("series", {}).keys()),
        "updated_utc": payload.get("fetched_utc")
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for pid, points in history.get("series", {}).items():
        obj = {"api": "bazarnama/v1", "id": pid, "unit": next((x.get("unit") for x in payload.get("items", []) if x.get("id") == pid), None),
               "updated_utc": payload.get("fetched_utc"), "points": [{"timestamp": p[0], "price": p[1]} for p in points]}
        (api / "history" / f"{pid}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


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
    if not isinstance(series, dict):
        series = {}
    seeded = set(data.get("seeded", [])) if isinstance(data, dict) else set()
    attempts = data.get("seed_attempted", {}) if isinstance(data, dict) else {}
    if not isinstance(attempts, dict):
        attempts = {}
    # Import provider history once per symbol; retain it across every future run.
    seed_history(series, [i.get("id") for i in items if i.get("id") in SITE_ASSETS], seeded, attempts)
    hour = int(time.time()) // 3600 * 3600
    for item in items:
        pid, price = item.get("id"), item.get("price")
        if not pid or not isinstance(price, (int, float)) or item.get("stale"):
            continue
        points = series.setdefault(pid, [])
        # One hourly observation at most; do not truncate historical records.
        if not points or points[-1][0] < hour:
            points.append([hour, float(price)])
    for pid, points in list(series.items()):
        unique = {int(p[0]): [int(p[0]), float(p[1])] for p in points if isinstance(p, (list, tuple)) and len(p) >= 2}
        series[pid] = sorted(unique.values(), key=lambda p: p[0])
    result = {"v": 2, "updated_utc": now_iso(), "seeded": sorted(seeded),
              "seed_attempted": attempts, "series": series}
    HIST.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return result


def main():
    try:
        primary = get_json(PRIMARY)
        if not valid_primary(primary):
            primary = None
    except Exception as e:  # noqa: BLE001
        print("primary failed:", e, file=sys.stderr)
        primary = None

    fx, fx_date = fetch_fx()
    iran_direct = fetch_iran_market()
    # The public Iran Market Data feed currently omits AED. Use Arzhaam's
    # published market quote as the independent AED fallback.
    arzhaam_aed_used = False
    if "aed" not in iran_direct:
        arzhaam_quote = fetch_arzhaam_aed()
        arzhaam_aed_used = "aed" in arzhaam_quote
        iran_direct.update(arzhaam_quote)
    cg = fetch_coingecko()
    eia = fetch_eia()
    stooq = fetch_stooq()

    if primary:
        payload = primary
        payload["primary_ok"] = True
    else:
        prev = load_json(OUT)
        if not valid_primary(prev):
            if not fx and not cg and not iran_direct:
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
    for pid in ("brent", "wti"):
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
        for pid, code in (("eur", "EUR"), ("gbp", "GBP")):
            cur = by_id.get(pid)
            has = cur and isinstance(cur.get("price"), (int, float)) and not cur.get("stale")
            per = fx.get(code)
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

    currency_checks = select_currency_quotes(items, iran_direct)
    payload["source_status"] = {"primary": bool(primary), "iran_market_data": sorted(k for k, v in iran_direct.items() if v.get("source_name") == "Iran Market Data"),
                                 "arzhaam_aed": arzhaam_aed_used,
                                 "currency_checks": currency_checks, "fx": bool(fx), "coingecko": sorted(cg),
                                "stooq": sorted(stooq), "eia": sorted(eia), "eia_key_set": bool(os.environ.get("EIA_API_KEY", "").strip())}
    payload["fetched_utc"] = now_iso()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    history = update_history(items)
    write_api_files(payload, history)
    s = build_summary(payload)
    if s:
        SUMMARY.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    print("Updated", OUT, "primary_ok =", payload["primary_ok"], "fx =", bool(fx), "coingecko =", sorted(cg), "stooq =", sorted(stooq), "eia =", sorted(eia))
    return 0


if __name__ == "__main__":
    sys.exit(main())
