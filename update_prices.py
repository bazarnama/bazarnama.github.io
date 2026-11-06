#!/usr/bin/env python3
"""Fetch latest prices and save them as static JSON for the site.

The browser reads data/prices.json first (fast, no rate-limit risk) and only
falls back to the live API when this file is missing or old. If the source is
down, the previous file is kept untouched, so the site always has a last value.
"""
import json, sys, urllib.request, datetime, pathlib

SOURCES = [
    "https://nerkhara.com/api/v1/latest.json",
]
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "prices.json"
SUMMARY = ROOT / "data" / "summary.json"
NAMES = {
    "usd": "دلار آمریکا", "eur": "یورو", "gbp": "پوند انگلیس", "aed": "درهم امارات",
    "gold-18k": "طلای 18 عیار", "coin-emami": "سکه امامی", "coin-half": "نیم‌سکه",
    "coin-quarter": "ربع‌سکه", "xau": "اونس جهانی طلا", "btc": "بیت‌کوین",
    "eth": "اتریوم", "brent": "نفت برنت", "wti": "نفت WTI",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "bazarnama-updater"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def valid(p):
    return isinstance(p, dict) and isinstance(p.get("items"), list) and any(
        isinstance(i, dict) and isinstance(i.get("price"), (int, float)) for i in p["items"])


def fa_pct(v):
    return f"{abs(v):.2f}"


def build_summary(payload):
    rows = []
    for i in payload["items"]:
        if i.get("id") in NAMES and isinstance(i.get("price"), (int, float)) and isinstance(i.get("change_pct"), (int, float)):
            rows.append((NAMES[i["id"]], i["change_pct"]))
    if not rows:
        return None
    rows.sort(key=lambda r: r[1])
    lines = []
    up = [r for r in rows if r[1] > 0]
    down = [r for r in rows if r[1] < 0]
    if up:
        n, v = up[-1]
        lines.append(f"بیشترین افزایش ۲۴ ساعت گذشته: {n} با {fa_pct(v)}٪.")
    if down:
        n, v = down[0]
        lines.append(f"بیشترین کاهش ۲۴ ساعت گذشته: {n} با {fa_pct(v)}٪.")
    lines.append(f"از {len(rows)} دارایی دارای تغییر معتبر، {len(up)} مورد مثبت و {len(down)} مورد منفی‌اند.")
    return {"generated_utc": payload.get("generated_utc"), "lines": lines}


def main():
    payload = None
    for url in SOURCES:
        try:
            p = fetch(url)
            if valid(p):
                payload = p
                break
        except Exception as e:  # noqa: BLE001
            print("source failed:", url, e, file=sys.stderr)
    if not payload:
        print("No valid data; keeping previous file.")
        return 0
    payload["fetched_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    s = build_summary(payload)
    if s:
        SUMMARY.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    print("Updated", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
