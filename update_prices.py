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
import json, os, statistics, sys, time, urllib.parse, urllib.request, datetime, pathlib, re, html
from zoneinfo import ZoneInfo

PRIMARY = "https://nerkhara.com/api/v1/latest.json"
SECONDARY_IRAN_MARKET = "https://raw.githubusercontent.com/iran-market/iran-market.github.io/main/data/popular.json"
DIRECT_CURRENCY_IDS = {"usd": "USD_IRR_FREE", "eur": "EUR_IRR_FREE", "gbp": "GBP_IRR_FREE", "aed": "AED_IRR_FREE"}
SITE_ASSETS = {"usd", "eur", "gbp", "aed", "usdt", "gold-18k", "coin-emami", "coin-half", "coin-quarter", "xau", "btc", "eth", "brent", "wti",
               "gold-24k", "gold-mesghal", "coin-bahar-azadi", "coin-gram", "silver-999", "xag", "xpt", "xpd", "paxg",
               "natural-gas", "opec-basket", "brent-spot", "wti-spot",
               "sol", "xrp", "bnb", "doge", "ltc", "trx", "ada", "ton", "bch", "dot"}
# Independent Iranian free-market quotes (never computed from the dollar). Used as a second source for
# usd/eur/gbp/aed and as the only source for the extra currencies below (shown on the currency page only).
NERKHSANJ = "https://nerkh.jahankhahan.shop/data/live.json"
NERKHSANJ_IDS = {"dollar": "usd", "euro": "eur", "pound": "gbp", "aed": "aed", "yuan": "cny", "lira": "try",
                 "cad": "cad", "aud": "aud", "chf": "chf", "sar": "sar", "tether": "usdt"}
EXTRA_DIRECT = {"cny", "try", "cad", "aud", "chf", "sar"}
DISCREPANCY_PCT = 5.0        # two independent quotes further apart than this are flagged
FX_URLS = [
    "https://api.frankfurter.dev/v1/latest?base=USD",
    "https://api.frankfurter.app/latest?from=USD",
]
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether"
             "&vs_currencies=usd&include_24hr_change=true")
CG_IDS = {"bitcoin": "btc", "ethereum": "eth", "tether": "usdt_usd"}

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data" / "prices.json"
HIST = ROOT / "data" / "history.json"               # lean file read by the site (last days, main assets only)
HIST_ARCHIVE = ROOT / "data" / "history-archive.json"  # full store, never read by the browser
HIST_RECENT_DAYS = 14        # hourly resolution is kept this long, older points become one per day
HIST_LEAN_DAYS = 8           # days published in the lean data/history.json
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

def jalali_text_to_tehran_epoch(date_text, time_text):
    """('1405/08/16', '19:35') in Tehran time -> epoch seconds, or None."""
    m = re.match(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$", str(date_text or ""))
    if not m:
        return None
    try:
        g = jalali_to_gregorian(*map(int, m.groups()))
    except Exception:  # noqa: BLE001
        return None
    hh = mm = 0
    t = re.match(r"^\s*(\d{1,2}):(\d{2})", str(time_text or ""))
    if t:
        hh, mm = int(t.group(1)), int(t.group(2))
    try:
        return datetime.datetime.combine(g, datetime.time(hh, mm), ZoneInfo("Asia/Tehran")).timestamp()
    except ValueError:
        return None


def fetch_nerkhsanj():
    """Independent direct Iranian free-market quotes (euro, pound, dirham, yuan, lira ...).

    The file carries a Jalali date and a Tehran clock time. An empty time means the market is closed
    (last close); such a quote is accepted for up to 72 h and keeps its real source date. A quote with a
    time is accepted for up to 3 h. Anything older is rejected, never shown as live.
    """
    try:
        d = get_json(NERKHSANJ)
        rates = d.get("rates") if isinstance(d, dict) else None
        if not isinstance(rates, dict):
            raise ValueError("unexpected NerkhSanj response")
        time_text = str(d.get("time") or "").strip()
        stamp = jalali_text_to_tehran_epoch(d.get("date"), time_text)
        if stamp is None:
            raise ValueError("no usable NerkhSanj timestamp")
        closed = not time_text
        if closed:
            stamp = min(stamp + 20.5 * 3600, time.time())   # a closed day: the quote is the evening close
        age = time.time() - stamp
        if age < -300 or age > (72 if closed else 3) * 3600:
            raise ValueError("NerkhSanj quote is stale")
        out = {}
        for key, pid in NERKHSANJ_IDS.items():
            try:
                price = float(str(rates.get(key)).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out[pid] = {"price": price, "unit": "IRT", "source_name": "NerkhSanj",
                        "source_updated_utc": datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "source_checked_utc": now_iso(), "method": "direct", "stale": False, "market_closed": closed}
        return out
    except Exception as e:  # noqa: BLE001
        print("NerkhSanj failed:", type(e).__name__, str(e)[:100], file=sys.stderr)
        return {}


def choose_independent(candidates):
    """candidates: quotes of ONE currency from independent sources, best source first.
    Returns (quote or None). Two or more quotes are cross-checked: the middle value defines
    'agreement'; a quote further than DISCREPANCY_PCT from it is an outlier. With exactly two quotes
    that disagree the first (preferred) source is kept and the discrepancy is reported."""
    cands = [c for c in candidates if c and isinstance(c.get("price"), (int, float)) and c["price"] > 0]
    if not cands:
        return None
    prices = [c["price"] for c in cands]
    med = statistics.median(prices)
    spread = (max(prices) - min(prices)) / med * 100 if len(cands) > 1 else None
    inliers = [c for c in cands if abs(c["price"] - med) / med * 100 <= DISCREPANCY_PCT] if len(cands) > 2 else cands
    if len(cands) == 2 and spread is not None and spread > DISCREPANCY_PCT:
        inliers = [cands[0]]
    chosen = dict(inliers[0])
    chosen["sources"] = len(inliers)
    chosen["checked_against"] = [c["source_name"] for c in cands if c is not inliers[0]]
    chosen["source_discrepancy_pct"] = round(spread, 3) if spread is not None else None
    chosen["discrepancy_warning"] = bool(spread is not None and spread > DISCREPANCY_PCT)
    return chosen


def write_if_changed(path, text):
    """Write only when the content differs, so unchanged files do not create new commits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except FileNotFoundError:
        pass
    path.write_text(text, encoding="utf-8")
    return True


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def is_derived(item):
    return bool(item.get("derived")) or item.get("method") == "derived"


def add_extra_currencies(items, ns):
    """yuan, lira, ... come only from an independent Iranian quote; never from usd x fx."""
    for pid in sorted(EXTRA_DIRECT):
        items[:] = [i for i in items if i.get("id") != pid]
        q = ns.get(pid)
        if q:
            row = dict(q)
            row.update({"id": pid, "change_pct": None, "updated_utc": q["source_updated_utc"], "sources": 1,
                        "source_selection": "direct-single"})
            items.append(row)


def prefer_direct_usdt(items, ns):
    """Tether: a direct quote beats a copy of the dollar price."""
    cur = next((i for i in items if i.get("id") == "usdt"), None)
    if ns.get("usdt") and (cur is None or cur.get("derived") or cur.get("stale")):
        row = dict(ns["usdt"])
        row.update({"id": "usdt", "change_pct": None, "updated_utc": row["source_updated_utc"], "sources": 1,
                    "source_selection": "direct-single"})
        if cur is not None:
            items[items.index(cur)] = row
        else:
            items.append(row)


KEEP_FROM_PRIMARY = {"usd", "usdt", "eur", "gbp", "aed"}   # NerkhAra is their first source (user's decision)


def drop_derived(items):
    """Public data must not contain dollar-cross calculations presented as market quotes.
    (A flagged copy of the dollar price is kept only for USDT when no direct tether quote exists.)"""
    def drop(i):   # our own usd x fx rows always go (except flagged USDT); NerkhAra's own derived rows only outside the kept ids
        return bool(i.get("derived") and i.get("id") != "usdt") or (i.get("method") == "derived" and i.get("id") not in KEEP_FROM_PRIMARY)
    removed = [i.get("id") for i in items if drop(i)]
    items[:] = [i for i in items if not drop(i)]
    return removed


def fill_changes_from_own_history(items, series):
    """24 h change from this site's own hourly points (same source family), when no source value exists."""
    now = time.time()
    target = now - 86400
    filled = 0
    for item in items:
        price = item.get("price")
        if item.get("stale") or isinstance(item.get("change_pct"), (int, float)) or not isinstance(price, (int, float)) or price <= 0:
            continue
        best = None
        for ts, val in series.get(item.get("id")) or []:
            # an hourly point recorded by this site (provider daily seeds sit exactly on UTC midnight)
            if abs(ts - target) <= 5400 and ts % 86400 != 0 and val > 0:
                if best is None or abs(ts - target) < abs(best[0] - target):
                    best = (ts, val)
        if best:
            item["change_pct"] = round((price - best[1]) / best[1] * 100, 3)
            item["change_basis"] = "own_history_24h"
            filled += 1
    print("Filled change_pct from own hourly history:", filled)


def select_currency_quotes(items, secondary):
    """Compare two independent quotes; reject derived EUR/GBP/AED values."""
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    checks = {}
    for pid in DIRECT_CURRENCY_IDS:
        primary = by_id.get(pid)
        alt = secondary.get(pid)
        p_ok = bool(primary and isinstance(primary.get("price"), (int, float)) and
                    not primary.get("stale") and not primary.get("derived"))   # NerkhAra's own method=derived is accepted
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
                           "sources": chosen.get("sources", 1),
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
        elif primary and pid in ("eur", "gbp", "aed") and primary.get("derived"):
            # Never publish a dollar-cross calculation as a direct Iranian free-market quote.
            items.remove(primary)
        elif primary:
            primary["stale"] = True
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
            primary["source_updated_utc"] = primary.get("updated_utc") or primary.get("as_of")
    return checks



def fill_missing_changes_from_source_history(items):
    """Fill missing change values from the same provider's daily history.

    Provider history is daily, so this fallback is day-over-day rather than an
    exact rolling 24-hour change. Never mix a secondary quote with NerkhAra history.
    """
    cache = {}
    filled = 0
    for item in items:
        if not isinstance(item, dict) or item.get("stale"):
            continue
        if isinstance(item.get("change_pct"), (int, float)):
            continue
        # A secondary quote must not be compared with another provider's history.
        if item.get("source_selection") == "secondary-direct" or item.get("backup_source"):
            continue
        history = item.get("history")
        url = history.get("json") if isinstance(history, dict) else None
        if not url and item.get("source_name", "NerkhAra") == "NerkhAra" and item.get("id"):
            url = f"https://nerkhara.com/api/v1/history/{urllib.parse.quote(str(item['id']))}.json"
        if not isinstance(url, str) or not url.startswith("https://nerkhara.com/api/v1/history/"):
            continue
        try:
            if url not in cache:
                cache[url] = get_json(url)
            raw = cache[url]
            points = raw.get("points", []) if isinstance(raw, dict) else []
            valid = []
            for point in points if isinstance(points, list) else []:
                if isinstance(point, (list, tuple)) and len(point) >= 2 and isinstance(point[0], str):
                    try:
                        price = float(point[1])
                    except (TypeError, ValueError):
                        continue
                    if price > 0:
                        valid.append((point[0], price))
            if len(valid) < 2:
                continue
            valid.sort(key=lambda x: x[0])
            latest_date, latest_price = valid[-1]
            previous = next(((day, price) for day, price in reversed(valid[:-1]) if day != latest_date), None)
            if not previous or previous[1] <= 0:
                continue
            previous_date, previous_price = previous
            item["change_pct"] = round((latest_price - previous_price) / previous_price * 100, 4)
            item["change_basis"] = "source_daily_history"
            item["change_history_dates"] = [previous_date, latest_date]
            filled += 1
        except Exception as e:  # noqa: BLE001
            print("source history failed for", item.get("id"), type(e).__name__, file=sys.stderr)
    print("Filled change_pct from source daily history:", filled)

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
    items = payload.get("items", [])
    write_if_changed(api / "latest.json", dumps({"api": "bazarnama/v1", "generated_utc": payload.get("generated_utc"),
                                                  "fetched_utc": payload.get("fetched_utc"), "items": items}))
    series = history.get("series", {})
    write_if_changed(api / "index.json", dumps({
        "api": "bazarnama/v1",
        "latest": "/api/v1/latest.json",
        "history_pattern": "/api/v1/history/{asset_id}.json",
        "assets": sorted(set([x.get("id") for x in items if x.get("id")])),
        "history_assets": sorted(series.keys()),
        "updated_utc": payload.get("fetched_utc")}))
    units = {x.get("id"): x.get("unit") for x in items}
    for pid, points in series.items():
        last = points[-1][0] if points else None
        obj = {"api": "bazarnama/v1", "id": pid, "unit": units.get(pid),
               "updated_utc": datetime.datetime.fromtimestamp(last, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if last else None,
               "points": [{"timestamp": p[0], "price": p[1]} for p in points]}
        write_if_changed(api / "history" / f"{pid}.json", dumps(obj))
    for f in (api / "history").glob("*.json"):     # remove history files of assets that no longer exist
        if f.stem not in series:
            f.unlink()


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
        lines.append(f"بیشترین افزایش 24 ساعت گذشته: {up[-1][0]} با {abs(up[-1][1]):.2f}%.")
    if down:
        lines.append(f"بیشترین کاهش 24 ساعت گذشته: {down[0][0]} با {abs(down[0][1]):.2f}%.")
    lines.append(f"از {len(rows)} دارایی دارای تغییر معتبر، {len(up)} مورد مثبت و {len(down)} مورد منفی‌اند.")
    return {"generated_utc": payload.get("generated_utc"), "lines": lines}


def compact_points(points, now):
    """Hourly resolution for the last HIST_RECENT_DAYS days; older points keep one value per UTC day."""
    cut = now - HIST_RECENT_DAYS * 86400
    daily = {}
    for p in points:
        if p[0] < cut:
            daily[p[0] // 86400] = p          # points are sorted, so the last one of the day wins
    return sorted(daily.values(), key=lambda p: p[0]) + [p for p in points if p[0] >= cut]


def update_history(items):
    """Full store -> data/history-archive.json (never read by the browser, compacted so it stays small).
    The site reads the lean data/history.json (last days of the main assets only)."""
    data = load_json(HIST_ARCHIVE)
    if not isinstance(data, dict):
        legacy = load_json(HIST)           # first run after the upgrade: migrate the old full file
        data = legacy if isinstance(legacy, dict) and not legacy.get("lean") else {}
    series = data.get("series", {})
    if not isinstance(series, dict):
        series = {}
    seeded = set(data.get("seeded", []))
    attempts = data.get("seed_attempted", {})
    if not isinstance(attempts, dict):
        attempts = {}
    # Import provider history once per symbol; retain it across every future run.
    seed_history(series, [i.get("id") for i in items if i.get("id") in SITE_ASSETS], seeded, attempts)
    now = time.time()
    hour = int(now) // 3600 * 3600
    for item in items:
        pid, price = item.get("id"), item.get("price")
        if not pid or not isinstance(price, (int, float)) or item.get("stale"):
            continue
        points = series.setdefault(pid, [])
        if not points or points[-1][0] < hour:     # at most one observation per hour
            points.append([hour, float(price)])
    keep = SITE_ASSETS | EXTRA_DIRECT | {i.get("id") for i in items if i.get("id")}
    for pid in [k for k in series if k not in keep]:
        del series[pid]                            # leftovers of removed (dollar-derived) currencies
    for pid, points in list(series.items()):
        unique = {int(p[0]): [int(p[0]), float(p[1])] for p in points if isinstance(p, (list, tuple)) and len(p) >= 2}
        series[pid] = compact_points(sorted(unique.values(), key=lambda p: p[0]), now)
    archive = {"v": 2, "seeded": sorted(seeded), "seed_attempted": attempts, "series": series}
    write_if_changed(HIST_ARCHIVE, dumps(archive))
    lean = {"v": 3, "lean": True, "series": {
        pid: [p for p in series[pid] if p[0] >= now - HIST_LEAN_DAYS * 86400] for pid in sorted(SITE_ASSETS) if pid in series}}
    write_if_changed(HIST, dumps(lean))
    return archive


def main():
    try:
        primary = get_json(PRIMARY)
        if not valid_primary(primary):
            primary = None
    except Exception as e:  # noqa: BLE001
        print("primary failed:", e, file=sys.stderr)
        primary = None

    fx, fx_date = fetch_fx()
    irm = fetch_iran_market()
    ns = fetch_nerkhsanj()
    # Arzhaam (public page) is only a last resort / third opinion for the dirham.
    arz = fetch_arzhaam_aed() if sum(1 for q in (irm.get("aed"), ns.get("aed")) if q) < 2 else {}
    iran_direct = {}
    for pid in DIRECT_CURRENCY_IDS:
        chosen = choose_independent([irm.get(pid), ns.get(pid), arz.get(pid)])
        if chosen:
            iran_direct[pid] = chosen
    cg = fetch_coingecko()
    eia = fetch_eia()
    stooq = fetch_stooq()

    if primary:
        payload = primary
        payload["primary_ok"] = True
    else:
        prev = load_json(OUT)
        if not valid_primary(prev):
            if not fx and not cg and not iran_direct and not ns:
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
    add_extra_currencies(items, ns)
    prefer_direct_usdt(items, ns)
    removed_derived = drop_derived(items)
    print("Removed dollar-derived items:", len(removed_derived))
    fill_missing_changes_from_source_history(items)
    payload["source_status"] = {"primary": bool(primary), "iran_market_data": sorted(irm), "nerkhsanj": sorted(ns),
                                 "arzhaam_aed": "aed" in arz,
                                 "currency_checks": currency_checks, "fx": bool(fx), "coingecko": sorted(cg),
                                 "stooq": sorted(stooq), "eia": sorted(eia),
                                 "eia_key_set": bool(os.environ.get("EIA_API_KEY", "").strip())}
    payload["fetched_utc"] = now_iso()
    history = update_history(items)
    fill_changes_from_own_history(items, history["series"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(payload), encoding="utf-8")
    write_api_files(payload, history)
    s = build_summary(payload)
    if s:
        write_if_changed(SUMMARY, json.dumps(s, ensure_ascii=False))
    print("Updated", OUT, "primary_ok =", payload["primary_ok"], "fx =", bool(fx), "coingecko =", sorted(cg), "stooq =", sorted(stooq), "eia =", sorted(eia))
    return 0


if __name__ == "__main__":
    sys.exit(main())
