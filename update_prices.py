#!/usr/bin/env python3
"""Fetch direct market quotes and publish timestamp-aware static JSON.

Iranian local prices must be provider-published direct market quotes. USD-derived
cross-rates are discarded. NerkhSanj is validation-only because its feed does not
separate direct market observations from exchange-rate-based estimates.
CoinGecko is a USD global-crypto fallback; EIA spot series are distributed via FRED CSV.
"""
import json, sys, time, urllib.parse, urllib.request, urllib.error, datetime, pathlib, re, csv, io
from zoneinfo import ZoneInfo

PRIMARY = "https://nerkhara.com/api/v1/latest.json"
NERKHSANJ_URL = "https://nerkh.jahankhahan.shop/data/live.json"
DIRECT_CURRENCY_IDS = {"usd", "eur", "gbp", "aed", "usdt"}
NERKHSANJ_IDS = {
    "dollar": "usd", "euro": "eur", "pound": "gbp", "aed": "aed",
    "yuan": "cny", "lira": "try", "cad": "cad", "aud": "aud",
    "chf": "chf", "sar": "sar", "tether": "usdt",
    "qar": "qar", "kwd": "kwd", "omr": "omr", "iqd": "iqd",
    "afn": "afn", "rub": "rub", "inr": "inr",
}
ADDITIONAL_CURRENCY_CHECKS = {"cny", "try", "cad", "aud", "chf", "sar", "qar", "kwd", "omr", "iqd", "afn", "rub", "inr"}
DISCREPANCY_PCT = 5.0

FRED_ENERGY_SERIES = {
    "brent-spot": ("DCOILBRENTEU", "USD/barrel", "Brent Europe spot"),
    "wti-spot": ("DCOILWTICO", "USD/barrel", "WTI Cushing spot"),
    "natural-gas": ("DHHNGSP", "USD/MMBtu", "Henry Hub natural gas spot"),
}

SITE_ASSETS = {"usd", "eur", "gbp", "aed", "usdt", "gold-18k", "coin-emami", "coin-half", "coin-quarter", "xau", "btc", "eth", "brent", "wti",
               "gold-24k", "gold-mesghal", "coin-bahar-azadi", "coin-gram", "silver-999", "xag", "xpt", "xpd", "paxg",
               "natural-gas", "opec-basket", "brent-spot", "wti-spot",
               "sol", "xrp", "bnb", "doge", "ltc", "trx", "ada", "ton", "bch", "dot"}

COINGECKO = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether,solana,ripple,binancecoin,dogecoin,litecoin,"
             "tron,cardano,the-open-network,bitcoin-cash,polkadot,pax-gold"
             "&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true")
CG_IDS = {"bitcoin": "btc", "ethereum": "eth", "tether": "usdt_usd", "solana": "sol", "ripple": "xrp", "binancecoin": "bnb",
          "dogecoin": "doge", "litecoin": "ltc", "tron": "trx", "cardano": "ada", "the-open-network": "ton",
          "bitcoin-cash": "bch", "polkadot": "dot", "pax-gold": "paxg"}


def fetch_fred_energy():
    """Fetch official daily spot references from FRED's public CSV export (no key)."""
    out = {}
    start_date = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=14)).isoformat()
    for pid, (series_id, unit, description) in FRED_ENERGY_SERIES.items():
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode({"id": series_id, "cosd": start_date})
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv", "User-Agent": "Mozilla/5.0 (compatible; Bazarnama/1.0)"})
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8-sig", "replace")
            rows = []
            for row in csv.DictReader(io.StringIO(raw)):
                date_value = row.get("observation_date") or row.get("DATE") or row.get("date")
                value = row.get(series_id) or row.get("value")
                if not date_value or value in (None, "", "."):
                    continue
                try:
                    price = float(value)
                    datetime.date.fromisoformat(date_value)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    rows.append((date_value, price))
            if not rows:
                raise ValueError("FRED returned no usable observations")
            date_value, price = rows[-1]
            change = None
            if len(rows) > 1 and rows[-2][1] > 0:
                change = round((price - rows[-2][1]) / rows[-2][1] * 100, 4)
            observed = date_value + "T00:00:00Z"
            history_points = [[int(parse_timestamp(day + "T00:00:00Z")), value] for day, value in rows]
            out[pid] = {
                "price": price, "unit": "USD", "display_unit": unit,
                "change_pct": change, "change_basis": "source_daily_history", "date": date_value,
                "updated_utc": observed, "source_updated_utc": observed,
                "source_checked_utc": now_iso(), "source_name": "EIA via FRED",
                "source_description": description, "source_time_label": f"تاریخ مشاهده بازار: {date_value}",
                "source_timestamp_kind": "observation_date", "method": "direct", "family": "energy",
                "backup_source": "fred", "market_type": "daily-spot", "delayed": True, "stale": False,
                "_history_points": history_points,
            }
        except Exception as exc:  # noqa: BLE001
            print("FRED energy failed for", pid, type(exc).__name__, file=sys.stderr)
    return out

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


def normalize_local_currency_unit(item):
    """Normalize only explicitly labelled rial/toman quotes; never infer units by ratio."""
    if not isinstance(item, dict):
        return None
    unit = str(item.get("unit") or "").strip().upper()
    try:
        price = float(item.get("price"))
    except (TypeError, ValueError):
        return None
    if not (price > 0 and price < 1e15):
        return None
    if unit in {"IRT", "TOMAN", "TOMANS"}:
        item["unit"] = "IRT"
    elif unit in {"IRR", "RIAL", "RIALS"}:
        item["price"] = price / 10.0
        item["unit"] = "IRT"
        item["unit_normalization"] = "IRR_to_IRT_divide_by_10"
    else:
        return None
    return item


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


def jalali_text_to_tehran_epoch(date_text, time_text):
    """Convert Jalali date + Tehran time into epoch seconds."""
    digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    date_text = str(date_text or "").translate(digits)
    time_text = str(time_text or "").translate(digits)
    match = re.match(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$", date_text)
    if not match:
        return None
    try:
        gregorian = jalali_to_gregorian(*map(int, match.groups()))
        clock = re.match(r"^\s*(\d{1,2}):(\d{2})", time_text)
        hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (0, 0)
        if hour > 23 or minute > 59:
            return None
        return datetime.datetime.combine(gregorian, datetime.time(hour, minute), ZoneInfo("Asia/Tehran")).timestamp()
    except (ValueError, OverflowError):
        return None


def fetch_nerkhsanj():
    """Fetch NerkhSanj figures for validation only; do not publish them as prices."""
    try:
        payload = get_json(NERKHSANJ_URL)
        rates = payload.get("rates") if isinstance(payload, dict) else None
        if not isinstance(rates, dict):
            raise ValueError("unexpected NerkhSanj response")
        date_text = str(payload.get("date") or "").strip()
        time_text = str(payload.get("time") or "").strip()
        closed = not bool(time_text)
        stamp = jalali_text_to_tehran_epoch(date_text, time_text or "19:30")
        if stamp is None:
            raise ValueError("NerkhSanj timestamp is missing or invalid")
        age = time.time() - stamp
        if age < -300 or age > (72 if closed else 3) * 3600:
            raise ValueError("NerkhSanj observation is too old")
        changes = payload.get("change") if isinstance(payload.get("change"), dict) else {}
        out = {}
        for source_key, pid in NERKHSANJ_IDS.items():
            try:
                price = float(str(rates.get(source_key)).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if not (0 < price < 1e15):
                continue
            try:
                change = float(changes[source_key]) if changes.get(source_key) is not None else None
            except (TypeError, ValueError):
                change = None
            out[pid] = {
                "price": price, "unit": "IRT", "family": "currency", "method": "direct",
                "source_name": "NerkhSanj (validation only)",
                "source_updated_utc": datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_time_label": f"{date_text} {time_text}".strip() if not closed else f"آخرین نرخ پایانی: {date_text}",
                "source_checked_utc": now_iso(), "stale": False, "market_closed": closed,
                "method": "validation-only", "change_pct": change,
            }
        return out
    except Exception as exc:  # noqa: BLE001
        print("NerkhSanj failed:", type(exc).__name__, file=sys.stderr)
        return {}


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


def drop_derived(items):
    """Never publish a calculated cross-rate as a direct market quote.

    This applies to every asset, including EUR/GBP/AED and USDT. If a direct
    quote is unavailable, the asset is omitted until a direct provider quote
    becomes available; the site must not copy or derive a price from USD.
    """
    removed = [i.get("id") for i in items if is_derived(i)]
    items[:] = [i for i in items if not is_derived(i)]
    # price_irt on a USDT/USD-quoted asset may be a cross-currency estimate;
    # without an explicit direct-local-market method, never expose it to the UI.
    for item in items:
        if str(item.get("unit") or "").upper() in {"USD", "USDT"}:
            item.pop("price_irt", None)
    return removed


def fill_changes_from_own_history(items, series):
    """24 h change from this site's own hourly points (same source family), when no source value exists."""
    now = time.time()
    target = now - 86400
    filled = 0
    for item in items:
        price = item.get("price")
        if item.get("stale") or item.get("backup_source") or isinstance(item.get("change_pct"), (int, float)) or not isinstance(price, (int, float)) or price <= 0:
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


def select_currency_quotes(items, validation_quotes):
    """Use NerkhSanj only as a cross-check, never as a published price source.

    Its public terms describe the figures as market observations and exchange-rate-based
    estimates, and the feed does not identify which individual values are estimates.
    NerkhAra remains the published source; only explicit direct/aggregated methods pass.
    """
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    checks = {}
    for pid in sorted(DIRECT_CURRENCY_IDS | ADDITIONAL_CURRENCY_CHECKS):
        primary = by_id.get(pid)
        alt = validation_quotes.get(pid)
        normalized_primary = normalize_local_currency_unit(primary) if primary else None
        p_ok = bool(normalized_primary and not primary.get("stale") and not is_derived(primary))
        a_ok = bool(alt and normalize_local_currency_unit(dict(alt)) and not alt.get("stale"))
        discrepancy = None
        if p_ok and a_ok:
            discrepancy = abs(float(primary["price"]) - float(alt["price"])) / float(primary["price"]) * 100
        checks[pid] = {
            "published_primary_available": p_ok,
            "validation_feed_available": a_ok,
            "discrepancy_pct": round(discrepancy, 3) if discrepancy is not None else None,
            "threshold_pct": DISCREPANCY_PCT,
            "validation_only": True,
        }
        if p_ok:
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
            primary["source_updated_utc"] = primary.get("source_updated_utc") or primary.get("updated_utc") or primary.get("as_of")
            primary["source_checked_utc"] = now_iso()
            primary["source_selection"] = "primary-direct"
            if a_ok:
                primary["validation_source"] = "NerkhSanj"
                primary["validation_price"] = alt["price"]
                primary["validation_discrepancy_pct"] = checks[pid]["discrepancy_pct"]
                primary["validation_warning"] = bool(discrepancy is not None and discrepancy > DISCREPANCY_PCT)
        elif primary and is_derived(primary):
            items.remove(primary)
            by_id.pop(pid, None)
        elif primary:
            primary["stale"] = True
            primary["source_name"] = primary.get("source_name") or "NerkhAra"
        # Crucially, a NerkhSanj-only value is not appended or substituted.
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
    source_map = data.get("source_map", {})
    if not isinstance(source_map, dict):
        source_map = {}
    # Import provider history once per symbol; retain it across every future run.
    seed_ids = [i.get("id") for i in items if i.get("id") in SITE_ASSETS
                and not i.get("backup_source")
                and i.get("source_name", "NerkhAra") == "NerkhAra"]
    seed_history(series, seed_ids, seeded, attempts)
    now = time.time()
    hour = int(now) // 3600 * 3600
    for item in items:
        pid, price = item.get("id"), item.get("price")
        history_points = item.pop("_history_points", [])
        if not pid or not isinstance(price, (int, float)) or item.get("stale"):
            continue
        source_key = "fred" if item.get("backup_source") == "fred" else (item.get("source_name") or "NerkhAra")
        previous_source = source_map.get(pid)
        if previous_source is None:
            # A fallback source must not be joined to a previous provider's series.
            if item.get("backup_source"):
                series[pid] = []
        elif previous_source != source_key:
            series[pid] = []
        source_map[pid] = source_key
        points = series.setdefault(pid, [])
        if source_key == "fred":
            existing_days = {int(p[0]) // 86400 for p in points}
            for stamp, value in history_points if isinstance(history_points, list) else []:
                if isinstance(stamp, (int, float)) and isinstance(value, (int, float)) and int(stamp) // 86400 not in existing_days:
                    points.append([int(stamp), float(value)])
                    existing_days.add(int(stamp) // 86400)
            observed = parse_timestamp(item.get("source_updated_utc") or item.get("updated_utc"))
            if observed is not None and int(observed) // 86400 not in existing_days:
                points.append([int(observed), float(price)])
        elif item.get("backup_source") in (None, "coingecko") and (not points or points[-1][0] < hour):
            points.append([hour, float(price)])
    keep = SITE_ASSETS | {i.get("id") for i in items if i.get("id")}
    for pid in [k for k in series if k not in keep]:
        del series[pid]                            # leftovers of removed (dollar-derived) currencies
    for pid, points in list(series.items()):
        unique = {int(p[0]): [int(p[0]), float(p[1])] for p in points if isinstance(p, (list, tuple)) and len(p) >= 2}
        series[pid] = compact_points(sorted(unique.values(), key=lambda p: p[0]), now)
    archive = {"v": 2, "seeded": sorted(seeded), "seed_attempted": attempts, "source_map": source_map, "series": series}
    write_if_changed(HIST_ARCHIVE, dumps(archive))
    lean = {"v": 3, "lean": True, "series": {
        pid: [p for p in series[pid] if p[0] >= now - HIST_LEAN_DAYS * 86400] for pid in sorted(SITE_ASSETS) if pid in series}}
    write_if_changed(HIST, dumps(lean))
    return archive



# Maximum acceptable source-data age. These are publication-aware guardrails, not
# promises about provider update cadence. The source timestamp is never replaced by
# the time our workflow happened to fetch the response.
FRESHNESS_LIMITS = {
    "crypto": 20 * 60,
    "currency": 90 * 60,
    "gold": 2 * 60 * 60,
    "coin": 2 * 60 * 60,
    "metal": 2 * 60 * 60,
    "energy": 2 * 60 * 60,
}
FRESHNESS_DEFAULT = 2 * 60 * 60


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
        if item.get("backup_source") == "fred":
            limit = 10 * 24 * 60 * 60  # EIA daily spot series; tolerate publication gaps and holidays.
        elif item.get("market_closed"):
            limit = 72 * 60 * 60  # retain the last close without calling it live
        elif item.get("id") == "opec-basket":
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
            "clock_basis": ("observation_date" if item.get("source_timestamp_kind") == "observation_date" else "provider_timestamp") if observed is not None else "unknown",
        }
        item["freshness"] = freshness
        item["source_checked_utc"] = item.get("source_checked_utc") or checked_iso
        rows.append({"id": item["id"], **freshness, "source": item.get("source_name") or item.get("source") or item.get("backup_source") or "NerkhAra"})
    policy = {**FRESHNESS_LIMITS, "fred_daily_spot": 10 * 24 * 60 * 60,
              "closed_market_last_quote": 72 * 60 * 60}
    return {"version": 2, "checked_utc": checked_iso, "policy": policy,
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
    except Exception as exc:  # noqa: BLE001
        print("NerkhAra primary failed:", type(exc).__name__, file=sys.stderr)
        primary = None

    # Independent direct Iranian market cross-check; no USD-derived rates.
    nerkhsanj_validation = fetch_nerkhsanj()
    cg = fetch_coingecko()
    fred_energy = fetch_fred_energy()

    if primary:
        payload = primary
        payload["primary_ok"] = True
    else:
        prev = load_json(OUT)
        if not valid_primary(prev):
            if not cg and not fred_energy:
                print("No valid source data; keeping existing files.")
                return 0
            prev = {"items": []}
        payload = prev
        payload["primary_ok"] = False
        for item in payload["items"]:
            item["stale"] = True

    items = payload["items"]
    annotate_freshness(items)
    by_id = {item.get("id"): item for item in items if isinstance(item, dict)}

    def missing_or_stale(pid):
        current = by_id.get(pid)
        return not (current and isinstance(current.get("price"), (int, float))
                    and current.get("price") > 0 and not current.get("stale") and not is_derived(current))

    # Independent crypto fallback is quoted in USD by CoinGecko, not converted to IRR.
    for key, quote in cg.items():
        if key == "usdt_usd" or not missing_or_stale(key):
            continue
        row = {"id": key, "family": "crypto", "price": quote["price"], "unit": "USD",
               "change_pct": quote.get("change_pct"), "updated_utc": quote.get("source_updated_utc"),
               "source_updated_utc": quote.get("source_updated_utc"), "source_checked_utc": now_iso(),
               "sources": 1, "backup_source": "coingecko", "source_name": "CoinGecko (global market)"}
        current = by_id.get(key)
        if current:
            items[items.index(current)] = row
        else:
            items.append(row)
        by_id[key] = row
    if "usdt_usd" in cg:
        payload["usdt_usd"] = cg["usdt_usd"]["price"]  # global USDT/USD reference only

    # EIA/FRED is the preferred direct source for physical Brent, physical WTI,
    # and Henry Hub spot. These are daily reference observations, not live futures.
    for pid, quote in fred_energy.items():
        current = by_id.get(pid)
        if current:
            items[items.index(current)] = quote
        else:
            items.append(quote)
        by_id[pid] = quote

    currency_checks = select_currency_quotes(items, nerkhsanj_validation)
    removed_derived = drop_derived(items)
    print("Removed calculated prices:", len(removed_derived))
    fill_missing_changes_from_source_history(items)

    payload["source_status"] = {
        "primary": bool(primary),
        "nerkhsanj_validation_quotes": sorted(nerkhsanj_validation),
        "nerkhsanj_used_for_published_prices": False,
        "currency_checks": currency_checks,
        "fx_cross_rates_used_for_prices": False,
        "derived_prices_published": False,
        "coingecko": sorted(cg),
        "fred_energy": sorted(fred_energy),
        "energy_spot_source": "EIA daily spot series via FRED public CSV; no API key; not real-time",
    }
    payload["fetched_utc"] = now_iso()
    freshness = annotate_freshness(items)
    payload["freshness"] = {"counts": freshness["counts"], "checked_utc": freshness["checked_utc"], "policy_version": 3}
    history = update_history(items)
    fill_changes_from_own_history(items, history["series"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(payload), encoding="utf-8")
    write_source_health(payload, freshness)
    write_api_files(payload, history)
    summary = build_summary(payload)
    if summary:
        write_if_changed(SUMMARY, json.dumps(summary, ensure_ascii=False))
    print("Updated", OUT, "primary_ok =", payload["primary_ok"], "coingecko =", sorted(cg), "fred_energy =", sorted(fred_energy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
