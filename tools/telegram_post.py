#!/usr/bin/env python3
"""Post a short price summary to a Telegram channel/group.

Needs two repository secrets: TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID (e.g. @my_channel;
the bot must be an admin of the channel). Without them the script only prints the message and exits 0,
so it can never break a workflow. Stale prices are left out, and nothing is posted when fewer than
3 fresh prices are available.

Usage: python3 tools/telegram_post.py [--dry-run]
"""
import json, os, pathlib, sys, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = "https://bazarnama.github.io"
LINES = [  # (asset id, label)
    ("usd", "دلار"), ("eur", "یورو"), ("gold-18k", "طلای 18 عیار"), ("coin-emami", "سکه امامی"),
    ("btc", "بیت‌کوین"), ("eth", "اتریوم"), ("xau", "انس طلا"), ("brent", "نفت برنت"),
]
UNITS = {"IRT": "تومان", "USD": "دلار", "USDT": "دلار"}


def fmt_price(price):
    return f"{price:,.0f}" if price >= 100 else f"{price:,.2f}"


def build_message(doc):
    """Return the message text, or None when there is not enough fresh data."""
    items = {i.get("id"): i for i in (doc or {}).get("items", []) if isinstance(i, dict)}
    rows = []
    for pid, label in LINES:
        it = items.get(pid)
        price = it.get("price") if it else None
        if not it or it.get("stale") or not isinstance(price, (int, float)) or price <= 0:
            continue
        ch = it.get("change_pct")
        arrow = ""
        if isinstance(ch, (int, float)) and ch != 0:
            arrow = f" {'🟢' if ch > 0 else '🔴'} {ch:+.2f}%"
        rows.append(f"{label}: {fmt_price(price)} {UNITS.get(str(it.get('unit')).upper(), it.get('unit') or '')}{arrow}")
    if len(rows) < 3:
        return None
    return "📊 قیمت‌های بازار\n\n" + "\n".join(rows) + f"\n\nجزئیات و نمودار: {SITE}\n#بازارنما"


def send(token, chat_id, text):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode()).get("ok") is True


def main():
    doc = json.loads((ROOT / "data" / "prices.json").read_text(encoding="utf-8"))
    text = build_message(doc)
    if not text:
        print("Not enough fresh prices; nothing posted.")
        return 0
    print(text)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if "--dry-run" in sys.argv or not token or not chat:
        print("(dry run: secrets missing or --dry-run)")
        return 0
    try:
        print("sent" if send(token, chat, text) else "Telegram refused the message")
    except Exception as e:  # noqa: BLE001
        print("Telegram error:", type(e).__name__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
