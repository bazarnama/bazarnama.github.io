#!/usr/bin/env python3
"""Fetch prices from several sources and save them as static JSON for the site.

Files written (all optional for the browser — it falls back to live APIs):
  data/prices.json   latest prices + global FX cross rates (+ backup crypto prices)
  data/history.json  hourly price history built by this script (one point per hour)
  data/summary.json  short automatic market summary

Sources
  1) NerkhAra latest.json          - Iranian market prices (primary)
  2) Frankfurter (ECB)             - global FX cross rates per 1 USD for reference only;
                                     never converted into local Iranian market quotes
  3) CoinGecko (public endpoint)   - backup BTC / ETH / USDT prices in USD
  4) Stooq CSV (no key)            - delayed futures prices for Brent / WTI
  5) EIA Open Data (US gov, needs a free key in env EIA_API_KEY) - external reference for
     Brent and WTI (daily); also fills them when the primary feed lacks them
If the primary source is down the previous prices are kept and flagged stale.
"""
import json, os, statistics, sys, time, urllib.parse, urllib.request, urllib.error, datetime, pathlib, re, html
from zoneinfo import ZoneInfo

PRIMARY = "https://nerkhara.com/api/v1/latest.json"
SECONDARY_IRAN_MARKET = "https://raw.githubusercontent.com/iran-market/iran-market.github.io/main/data/popular.json"
DIRECT_CURRENCY_IDS = {"usd": "USD_IRR_FREE", "eur": "EUR_IRR_FREE", "gbp": "GBP_IRR_FREE", "aed": "AED_IRR_FREE"}
SITE_ASSETS = {"usd", "eur", "gbp", "aed", "usdt", "gold-18k", "coin-emami", "coin-half", "coin-quarter", "xau", "btc", "eth", "brent", "wti",
               "gold-24k", "gold-mesghal", "coin-bahar-azadi", "coin-gram", "silver-999", "xag", "xpt", "xpd", "paxg",
               "natural-gas", "opec-basket", "brent-spot", "wti-spot",
               "sol", "xrp", "bnb", "doge", "ltc", "trx", "ada", "ton", "bch", "dot"}
# NerkhAra is the primary source for USD/EUR/GBP/AED. Arzhaam is the ONLY
# fallback for those four currencies. NerkhSanj is reserved for extra currencies
# (CNY/TRY/CAD/AUD/CHF/SAR) and direct USDT; it must not replace these four quotes.
NERKHSANJ = "https://nerkh.jahankhahan.shop/data/live.json"
NERKHSANJ_IDS = {"dollar": "usd", "euro": "eur", "pound": "gbp", "aed": "aed", "yuan": "cny", "lira": "try",
                 "cad": "cad", "aud": "aud", "chf": "chf", "sar": "sar", "tether": "usdt"}
EXTRA_DIRECT = {"cny", "try", "cad", "aud", "chf", "sar"}
DISCREPANCY_PCT = 5.0        # two independent quotes further apart than this are flagged
FX_URLS = [
    "https://api.frankfurter.dev/v1/latest?base=USD",
    "https://api.frankfurter.app/latest?from=USD",
]
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,solana,ripple,binancecoin,dogecoin,litecoin,"
             "tron,cardano,the-open-network,bitcoin-cash,polkadot,pax-gold"
             "&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true")
CG_IDS = {"bitcoin": "btc", "ethereum": "eth", "tether": "usdt_usd", "solana": "sol", "ripple": "xrp", "binancecoin": "bnb",
          "dogecoin": "doge", "litecoin": "ltc", "tron": "trx", "cardano": "ada", "the-open-network": "ton",
          "bitcoin-cash": "bch", "polkadot": "dot", "pax-gold": "paxg"}

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data" / "prices.json"
HIST = ROOT / "data" / "history.json"               # lean file read by the site (last days, main assets only)
HIST_ARCHIVE = ROOT / "data" / "history-archive.json"  # full store, never read by the browser
HIST_RECENT_DAYS = 14        # hourly resolution is kept this long, older points become one per day
HIST_LEAN_DAYS = 8           # days published in the lean data/history.json
SUMMARY = ROOT / "data" / "summary.json"
SOURCE_HEALTH = ROOT / "data" / "source-health.json"
HIST_MAX = None  # preserve the full series; old points are never discarded

NAMES = {
    "usd": "دلار آمریکا", "eur": "یورو", "gbp": "پوند انگلیس", "aed": "درهم امارات", "usdt": "تتر",
    "gold-18k": "طلای 18 عیار", "coin-emami": "سکه امامی", "coin-half": "نیم‌سکه",
    "coin-quarter": "ربع‌سکه", "xau": "اونس جهانی طلا", "btc": "بیت‌کوین",
    "eth": "اتریوم", "brent": "نفت برنت", "wti": "نفت WTI",
}


def get_json(url):
    """Fetch JSON with one bounded retry for transient network/rate-limit failures."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "bazarnama-updater"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if attempt or exc.code not in (429, 500, 502, 503, 504):
                raise
            retry_after = exc.headers.get("Retry-After", "")
            try:
                delay = min(5.0, max(1.0, float(retry_after)))
            except (TypeError, ValueError):
                delay = 1.0
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt:
                raise
            time.sleep(1.0)
    raise RuntimeError("JSON fetch failed after retry")


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
            out[key] = {"price": float(row["usd"]), "change_pct": row.get("usd_24h_change"),
                        "source_updated_utc": datetime.datetime.fromtimestamp(float(row["last_updated_at"]), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(row.get("last_updated_at"), (int, float)) else None}
    return out


EIA_SERIES = [  # (id, route, series code, unit)
    ("brent", "petroleum/pri/spt", "RBRTE", "USD"),
    ("wti", "petroleum/pri/spt", "RWTC", "USD"),
]

FRED_SERIES = {
    "brent-spot": ("DCOILBRENTEU", "USD"),
    "wti-spot": ("DCOILWTICO", "USD"),
    "natural-gas": ("DHHNGSP", "USD/MMBtu"),
}


def fetch_fred_energy():
    """Fetch daily physical spot references from FRED's public CSV endpoint (no API key)."""
    out = {}
    for asset_id, (series_id, unit) in FRED_SERIES.items():
        try:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode({"id": series_id})
            req = urllib.request.Request(url, headers={"User-Agent": "bazarnama-updater"})
            with urllib.request.urlopen(req, timeout=20) as response:
                lines = response.read().decode("utf-8-sig", "replace").strip().splitlines()
            if len(lines) < 2:
                continue
            rows = []
            for line in lines[1:]:
                parts = line.split(",", 1)
                if len(parts) != 2:
                    continue
                date_text, raw = parts[0].strip(), parts[1].strip().strip('"')
                try:
                    value = float(raw)
                    datetime.date.fromisoformat(date_text)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    rows.append((date_text, value))
            if not rows:
                continue
            rows.sort(key=lambda x: x[0])
            date_text, price = rows[-1]
            previous = rows[-2][1] if len(rows) > 1 else None
            change = (price - previous) / previous * 100 if previous else None
            out[asset_id] = {
                "price": price, "unit": unit, "date": date_text,
                "source_name": "FRED", "backup_source": "fred",
                "market_type": "daily-spot", "change_pct": round(change, 4) if change is not None else None,
                "source_updated_utc": date_text + "T00:00:00Z",
                "_history_points": rows,
            }
        except Exception as exc:  # noqa: BLE001
            print("FRED failed for", asset_id, type(exc).__name__, file=sys.stderr)
    return out


def normalize_local_currency_unit(row):
    """Normalize only explicitly labeled IRR values to toman; never guess by magnitude."""
    if not isinstance(row, dict):
        return None
    unit = str(row.get("unit") or "").strip().upper()
    if unit == "IRR":
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            return None
        normalized = dict(row)
        normalized["price"] = price / 10
        normalized["unit"] = "IRT"
        normalized["unit_normalization"] = "IRR_to_IRT_divide_by_10"
        return normalized
    if unit == "IRT":
        return dict(row)
    return None


STOOQ_SYMBOLS = {  # id -> candidate symbols (first plausible one wins), plausible price range
    "brent": (["cb.f", "lco.f"], 10, 400),
    "wti": (["cl.f"], 10, 400),
    # backups for metals / gas: only requested when NerkhAra has no fresh value for them
    "xau": (["xauusd"], 500, 30000),
    "xag": (["xagusd"], 5, 1000),
    "xpt": (["xptusd"], 200, 15000),
    "xpd": (["xpdusd"], 200, 15000),
    "natural-gas": (["ng.f"], 0.3, 60),
}
STOOQ_ALWAYS = ("brent", "wti")   # references shown even when the primary feed is fine


def fetch_stooq(ids=None):
    """Delayed futures prices (a few minutes to ~20 min late) from Stooq CSV. No key needed.
    ids: which ids to request (default: the always-on energy references)."""
    out = {}
    for pid in (ids if ids is not None else STOOQ_ALWAYS):
        if pid not in STOOQ_SYMBOLS:
            continue
        symbols, lo, hi = STOOQ_SYMBOLS[pid]
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
                out[pid] = {"price": price, "unit": "USD", "source_date": row.get("date"), "source_time": row.get("time"),
                            "source_updated_utc": None, "symbol": sym, "source": "Stooq"}
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
            explicit_unit = str(row.get("unit") or "").strip().upper()
            if explicit_unit:
                normalized = normalize_local_currency_unit({"price": price, "unit": explicit_unit})
                if normalized is None:
                    continue
                price = normalized["price"]
            # Iran Market Data's documented default quote unit is toman (IRT).
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


def fetch_arzhaam_currencies():
    """Fetch direct USD/EUR/GBP/AED quotes from Arzhaam as NerkhAra's fallback.

    NerkhAra is always primary. Arzhaam is the only fallback for these four
    currency IDs; NerkhSanj and other feeds are deliberately excluded.
    Each page is parsed independently so one failure never blocks the others.
    """
    urls = {pid: f"https://arzhaam.ir/rates/{pid}" for pid in DIRECT_CURRENCY_IDS}
    months = {"فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5,
              "شهریور": 6, "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10,
              "بهمن": 11, "اسفند": 12}
    digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    out = {}

    for pid, url in urls.items():
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 (compatible; BazarnamaPriceBot/1.0)",
            })
            with urllib.request.urlopen(req, timeout=20) as response:
                page = response.read().decode("utf-8", "replace")

            # Keep visible page text only; normalize Persian/Arabic digits and separators.
            page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
            visible = html.unescape(re.sub(r"<[^>]+>", " ", page))
            visible = re.sub(r"\s+", " ", visible).translate(digit_map)
            visible = visible.replace("٬", ",").replace("٫", ".")

            # Each /rates/<assetId> page is for one asset, so its displayed toman
            # quote is the first price followed by the unit label.
            price_match = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*تومان", visible)
            time_match = re.search(
                r"آخرین\s*به[\u200c ]?روزرسانی\s*[:：]?\s*(\d{1,2})\s+([آ-ی]+)\s+(\d{4})[،, ]+\s*(\d{1,2}):(\d{2})",
                visible,
            )
            if not price_match or not time_match:
                raise ValueError("public page has no parseable price/timestamp")

            price = float(price_match.group(1).replace(",", ""))
            # Broad safety bounds reject malformed page fragments, not market movements.
            if not (100 <= price <= 100_000_000):
                raise ValueError("quote outside plausible toman bounds")

            day, month_name, year, hour, minute = time_match.groups()
            if month_name not in months or int(day) < 1 or int(hour) > 23 or int(minute) > 59:
                raise ValueError("invalid Jalali source timestamp")
            gregorian = jalali_to_gregorian(int(year), months[month_name], int(day))
            tehran = datetime.datetime.combine(
                gregorian, datetime.time(int(hour), int(minute)), ZoneInfo("Asia/Tehran")
            )
            age = (datetime.datetime.now(ZoneInfo("Asia/Tehran")) - tehran).total_seconds()
            if age < -300 or age > 6 * 60 * 60:
                raise ValueError("Arzhaam quote is outside the six-hour freshness window")

            out[pid] = {
                "price": price, "unit": "IRT", "source_name": "Arzhaam",
                "source_updated_utc": tehran.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_checked_utc": now_iso(), "method": "direct", "stale": False,
                "source_url": url,
            }
        except Exception as exc:  # noqa: BLE001 - one page failure must not abort the workflow
            print(f"Arzhaam {pid} fallback failed: {type(exc).__name__}", file=sys.stderr)
    return out


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
    """Fetch direct quotes for extra currencies and USDT from NerkhSanj.

    NerkhSanj is NOT a source for USD/EUR/GBP/AED. Those four use NerkhAra
    first and Arzhaam only as fallback. The file carries a Jalali date and a
    Tehran clock time; stale quotes are retained only for diagnostics.
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
        if age < -300 or age > 7 * 24 * 3600:
            raise ValueError("NerkhSanj timestamp is outside the diagnostic retention window")
        out = {}
        for key, pid in NERKHSANJ_IDS.items():
            try:
                price = float(str(rates.get(key)).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            change_key = key
            change = (d.get("change") or {}).get(change_key) if isinstance(d.get("change"), dict) else None
            try:
                change = float(change) if change is not None else None
            except (TypeError, ValueError):
                change = None
            out[pid] = {"price": price, "unit": "IRT", "source_name": "NerkhSanj",
                        "source_updated_utc": datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "source_checked_utc": now_iso(), "method": "direct", "change_pct": change,
                        "stale": age > (72 if closed else 3) * 3600, "market_closed": closed}
        return out
    except Exception as e:  # noqa: BLE001
        print("NerkhSanj failed:", type(e).__name__, str(e)[:100], file=sys.stderr)
        return {}


def choose_independent(candidates):
    """candidates: quotes of ONE currency from independent sources, best source first.
    Returns (quote or None). Two or more quotes are cross-checked: the middle value defines
    'agreement'; a quote further than DISCREPANCY_PCT from it is an outlier. With exactly two quotes
    that disagree the first (preferred) source is kept and the discrepancy is reported."""
    cands = [c for c in candidates if c and not c.get("stale") and
             isinstance(c.get("price"), (int, float)) and c["price"] > 0]
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
        if q and not q.get("stale"):
            row = dict(q)
            row.update({"id": pid, "change_pct": None, "updated_utc": q["source_updated_utc"], "sources": 1,
                        "source_selection": "direct-single"})
            items.append(row)


def prefer_direct_usdt(items, ns):
    """Tether: a direct quote beats a copy of the dollar price."""
    cur = next((i for i in items if i.get("id") == "usdt"), None)
    if ns.get("usdt") and not ns["usdt"].get("stale") and (cur is None or cur.get("derived") or cur.get("stale")):
        row = dict(ns["usdt"])
        row.update({"id": "usdt", "change_pct": None, "updated_utc": row["source_updated_utc"], "sources": 1,
                    "source_selection": "direct-single"})
        if cur is not None:
            items[items.index(cur)] = row
        else:
            items.append(row)


def drop_derived(items):
    """Public data must not contain dollar-cross calculations presented as market quotes.
    (A flagged copy of the dollar price is kept only for USDT when no direct tether quote exists.)"""
    def drop(i):
        return bool(i.get("derived") and i.get("id") != "usdt") or i.get("method") == "derived"
    removed = [i.get("id") for i in items if drop(i)]
    items[:] = [i for i in items if not drop(i)]
    for item in items:
        if str(item.get("unit") or "").upper() == "USDT":
            item.pop("price_irt", None)
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


def select_currency_quotes(items, fallback):
    """Keep fresh NerkhAra quotes; use Arzhaam only if primary is missing/stale/derived.

    The fallback mapping passed here must contain Arzhaam quotes only. NerkhSanj
    is intentionally not eligible for USD/EUR/GBP/AED under any condition.
    """
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    checks = {}
    for pid in DIRECT_CURRENCY_IDS:
        primary = by_id.get(pid)
        alt = fallback.get(pid)
        p_ok = bool(primary and isinstance(primary.get("price"), (int, float)) and
                    not primary.get("stale") and not primary.get("derived") and primary.get("method") != "derived")
        a_ok = bool(alt and isinstance(alt.get("price"), (int, float)) and
                    not alt.get("stale") and alt.get("method") != "derived")
        discrepancy = None
        if p_ok and a_ok and primary.get("price"):
            discrepancy = abs(float(primary["price"]) - float(alt["price"])) / float(primary["price"]) * 100
        checks[pid] = {
            "primary_available": p_ok, "secondary_available": a_ok,
            "discrepancy_pct": round(discrepancy, 3) if discrepancy is not None else None,
            "threshold_pct": 5.0,
        }
        # Arzhaam may replace only a missing, stale, invalid, or derived NerkhAra quote.
        # A fresh NerkhAra quote is always authoritative, regardless of disagreement.
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
                primary["validation_source"] = alt.get("source_name", "independent source")
                primary["validation_price"] = alt["price"]
                primary["source_discrepancy_pct"] = checks[pid]["discrepancy_pct"]
                primary["validation_warning"] = discrepancy is not None and discrepancy > DISCREPANCY_PCT
                primary["discrepancy_warning"] = primary["validation_warning"]
        elif primary and (primary.get("derived") or primary.get("method") == "derived"):
            # No fresh direct backup exists; remove the derived value instead of publishing an estimate.
            items.remove(primary)
        elif primary:
            primary["stale"] = True
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
            primary["source_updated_utc"] = primary.get("updated_utc") or primary.get("as_of")
    return checks




def apply_arzhaam_currency_priority(items, arz):
    """Compatibility wrapper for the explicit NerkhAra -> Arzhaam priority."""
    return select_currency_quotes(items, arz)


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
                                                  "fetched_utc": payload.get("fetched_utc"), "freshness": payload.get("freshness"), "items": items}))
    health_path = ROOT / "data" / "source-health.json"
    if health_path.exists():
        write_if_changed(api / "source-health.json", health_path.read_text(encoding="utf-8"))
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



# Maximum acceptable source-data age. These are publication-aware guardrails, not
# promises about provider update cadence. The source timestamp is never replaced by
# the time our workflow happened to fetch the response.
FRESHNESS_LIMITS = {
    "crypto": 45 * 60,
    "currency": 3 * 60 * 60,
    "gold": 4 * 60 * 60,
    "coin": 4 * 60 * 60,
    "metal": 4 * 60 * 60,
    "energy": 6 * 60 * 60,
}
FRESHNESS_DEFAULT = 4 * 60 * 60


def item_source_epoch(item):
    """Return provider observation time; never substitute fetched_utc/generated_utc."""
    for key in ("source_updated_utc", "updated_utc", "as_of"):
        stamp = parse_timestamp(item.get(key))
        if stamp is not None:
            return stamp
    value = item.get("date")
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return parse_timestamp(value + "T00:00:00Z")
    return None


def annotate_freshness(items, checked_at=None):
    checked_at = checked_at or time.time()
    checked_iso = datetime.datetime.fromtimestamp(checked_at, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    statuses = {"fresh": 0, "aging": 0, "stale": 0, "unknown": 0}
    rows = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        family = str(item.get("family") or "").lower()
        limit = FRESHNESS_LIMITS.get(family, FRESHNESS_DEFAULT)
        # Arzhaam's public market pages can publish a quote less frequently than
        # NerkhAra. fetch_arzhaam_currencies() already rejects quotes older than
        # six hours; use that same explicit ceiling here instead of the generic
        # 90-minute currency limit, which incorrectly relabelled valid fallback
        # quotes (for example, a 21:00 quote checked at 23:10) as stale.
        if item.get("source_name") == "Arzhaam":
            limit = 6 * 60 * 60
        if item.get("backup_source") in {"eia", "fred"}:
            limit = 72 * 60 * 60  # EIA/FRED benchmark series are daily publications.
        elif item.get("id") in {"opec-basket", "natural-gas"}:
            limit = 4 * 24 * 60 * 60
        observed = item_source_epoch(item)
        if observed is None:
            status, age = ("stale", None) if item.get("stale") else ("unknown", None)
        else:
            age = max(0, int(checked_at - observed))
            if item.get("stale") or age > limit:
                status = "stale"
                item["stale"] = True
            elif age > limit * 0.65:
                status = "aging"
            else:
                status = "fresh"
        statuses[status] += 1
        freshness = {
            "status": status,
            "observed_utc": datetime.datetime.fromtimestamp(observed, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if observed is not None else None,
            "checked_utc": checked_iso,
            "age_seconds": age,
            "max_age_seconds": limit,
            "clock_basis": "provider_timestamp" if observed is not None else "unknown",
        }
        item["freshness"] = freshness
        item["source_checked_utc"] = item.get("source_checked_utc") or checked_iso
        rows.append({"id": item["id"], **freshness, "source": item.get("source_name") or item.get("source") or item.get("backup_source") or "NerkhAra"})
    return {"version": 1, "checked_utc": checked_iso, "policy": FRESHNESS_LIMITS,
            "counts": statuses, "assets": rows}


def write_source_health(payload, health):
    health_doc = {
        "schema": "bazarnama/source-health/v1",
        "generated_utc": payload.get("generated_utc"),
        "fetched_utc": payload.get("fetched_utc"),
        "primary_ok": bool(payload.get("primary_ok")),
        "source_status": payload.get("source_status", {}),
        "freshness": health,
        "notes": [
            "observed_utc is the provider's data timestamp, not the time Bazarnama fetched it",
            "unknown means the provider did not supply a trustworthy timestamp",
            "aging and stale thresholds vary by market and publication cadence",
        ],
    }
    write_if_changed(SOURCE_HEALTH, dumps(health_doc))


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
    # Strict source order for USD/EUR/GBP/AED:
    #   1) NerkhAra latest.json (primary payload)
    #   2) Arzhaam public rates pages (the ONLY fallback)
    # NerkhSanj and Iran Market Data must never become the source of these four.
    arz = fetch_arzhaam_currencies()
    iran_direct = {pid: arz[pid] for pid in DIRECT_CURRENCY_IDS if pid in arz}
    cg = fetch_coingecko()
    eia = fetch_eia()
    fred = fetch_fred_energy()
    stooq = {}

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
    # Apply source-age checks before fallback selection. This is important: a provider
    # can return HTTP 200 with an old quote, which must trigger a fresher backup.
    annotate_freshness(items)
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}

    def _missing(pid):   # NerkhAra stays the first source: backups are used only when it has no fresh value
        cur = by_id.get(pid)
        return not (cur and isinstance(cur.get("price"), (int, float)) and cur.get("price") > 0 and not cur.get("stale"))

    need = [pid for pid in STOOQ_SYMBOLS if pid not in STOOQ_ALWAYS and _missing(pid)]
    stooq = fetch_stooq(list(STOOQ_ALWAYS) + need)

    # backup crypto prices (USD) when the primary feed does not have them
    for key in [k for k in cg if k != "usdt_usd"]:
        if _missing(key):
            row = {"id": key, "family": "crypto", "price": cg[key]["price"], "unit": "USD",
                   "change_pct": cg[key].get("change_pct"), "updated_utc": cg[key].get("source_updated_utc"), "source_updated_utc": cg[key].get("source_updated_utc"),
                   "source_checked_utc": now_iso(), "sources": 1, "backup_source": "coingecko", "source_name": "CoinGecko (جایگزین)"}
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
    if any(k in stooq for k in STOOQ_ALWAYS):
        payload["delayed_energy"] = {k: v for k, v in stooq.items() if k in STOOQ_ALWAYS}
    for pid in ("brent", "wti", "brent-spot", "wti-spot", "xau", "xag", "xpt", "xpd", "natural-gas"):
        cur = by_id.get(pid)
        has = cur and isinstance(cur.get("price"), (int, float)) and not cur.get("stale")
        if has:
            continue
        if pid in stooq:
            e = stooq[pid]
            row = {"id": pid, "family": "energy" if pid in {"brent", "wti", "brent-spot", "wti-spot", "natural-gas"} else "metal", "price": e["price"], "unit": e["unit"], "change_pct": None,
                   "updated_utc": e.get("source_updated_utc"), "source_updated_utc": e.get("source_updated_utc"),
                   "source_checked_utc": now_iso(), "sources": 1, "backup_source": "stooq", "delayed": True,
                   "source_name": "Stooq (جایگزین)"}
        elif pid in eia:
            e = eia[pid]
            row = {"id": pid, "family": "energy", "price": e["price"], "unit": e["unit"], "change_pct": e["change_pct"],
                   "updated_utc": e["date"] + "T00:00:00Z", "source_updated_utc": e["date"] + "T00:00:00Z",
                   "source_checked_utc": now_iso(), "sources": 1, "backup_source": "eia", "delayed": True}
        elif pid in fred:
            e = fred[pid]
            row = {"id": pid, "family": "energy", "price": e["price"], "unit": e["unit"], "change_pct": e["change_pct"],
                   "updated_utc": e["source_updated_utc"], "source_updated_utc": e["source_updated_utc"],
                   "source_checked_utc": now_iso(), "sources": 1, "backup_source": "fred", "source_name": "FRED (جایگزین)",
                   "delayed": True, "market_type": e["market_type"]}
        else:
            continue
        if cur:
            items[items.index(cur)] = row
        else:
            items.append(row)
        by_id[pid] = row

    if fx:
        payload["fx_usd"] = fx
        payload["fx_date"] = fx_date

    # Resolve USD from the current item list immediately before the USDT fallback.
    # Do not rely on a variable created in another branch: the previous version
    # referenced `usd` without ever defining it, which crashed every workflow run.
    usd = next(
        (item for item in items
         if isinstance(item, dict) and item.get("id") == "usd"),
        None,
    )
    existing_price_ids = {
        item.get("id") for item in items
        if isinstance(item, dict)
        and isinstance(item.get("price"), (int, float))
        and item.get("price") > 0
    }
    if (
        usd
        and isinstance(usd.get("price"), (int, float))
        and usd.get("price") > 0
        and not usd.get("stale")
        and "usdt" not in existing_price_ids
    ):
        # This is explicitly marked derived and is removed/replaced below if a
        # direct USDT quote is available. It must never masquerade as a direct quote.
        items.append({
            "id": "usdt",
            "price": usd["price"],
            "unit": usd.get("unit", "IRT"),
            "change_pct": usd.get("change_pct"),
            "updated_utc": usd.get("updated_utc"),
            "sources": 0,
            "derived": True,
            "derived_from": "usd",
        })

    currency_checks = select_currency_quotes(items, iran_direct)
    # Strictly preserves NerkhAra first; Arzhaam is the only eligible fallback.
    add_extra_currencies(items, ns)
    prefer_direct_usdt(items, ns)
    removed_derived = drop_derived(items)
    print("Removed dollar-derived items:", len(removed_derived))
    fill_missing_changes_from_source_history(items)
    payload["source_status"] = {"primary": bool(primary), "iran_market_data": sorted(irm), "nerkhsanj": sorted(ns),
                                 "arzhaam_currencies": sorted(arz),
                                 "currency_checks": currency_checks, "fx": bool(fx), "coingecko": sorted(cg),
                                 "stooq": sorted(stooq), "eia": sorted(eia), "fred": sorted(fred),
                                 "eia_key_set": bool(os.environ.get("EIA_API_KEY", "").strip())}
    payload["fetched_utc"] = now_iso()
    freshness = annotate_freshness(items)
    payload["freshness"] = {"counts": freshness["counts"], "checked_utc": freshness["checked_utc"], "policy_version": 1}
    history = update_history(items)
    fill_changes_from_own_history(items, history["series"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(payload), encoding="utf-8")
    write_source_health(payload, freshness)
    write_api_files(payload, history)
    s = build_summary(payload)
    if s:
        write_if_changed(SUMMARY, json.dumps(s, ensure_ascii=False))
    print("Updated", OUT, "primary_ok =", payload["primary_ok"], "fx =", bool(fx), "coingecko =", sorted(cg), "stooq =", sorted(stooq), "eia =", sorted(eia))
    return 0


if __name__ == "__main__":
    sys.exit(main())
