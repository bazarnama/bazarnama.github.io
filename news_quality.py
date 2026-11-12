"""News relevance, categorisation, de-duplication and date handling (pure functions, no network).

Design rules
- A headline is published only if it is really about the economy: strong economic terms, or at least two weak
  ones. A weak word alone ("بازار", "قیمت", "بانک") is not enough, and matching is on whole words, so
  "بازاریان" is not "بازار".
- Nothing is invented: no generated summaries, no quotes. We keep title, source name, link and the date the
  publisher gave. Items without a trustworthy date are not published.
"""
import re
from datetime import datetime, timezone, timedelta

STRONG = 2
WEAK = 1
THRESHOLD = 2

# category -> (label, {phrase: weight})
CATEGORIES = {
    "currency": ("ارز", {"دلار": STRONG, "یورو": STRONG, "درهم": STRONG, "پوند": STRONG, "نرخ ارز": STRONG, "بازار ارز": STRONG,
                         "ارز": STRONG, "ارزی": STRONG, "صرافی": STRONG, "بانک مرکزی": STRONG, "ارز مبادله ای": STRONG}),
    "gold": ("طلا و سکه", {"طلا": STRONG, "سکه": STRONG, "شمش": STRONG, "اونس": STRONG, "گرم طلا": STRONG, "بازار طلا": STRONG}),
    "stock": ("بورس", {"بورس": STRONG, "فرابورس": STRONG, "سهام": STRONG, "شاخص کل": STRONG, "سهامداران": STRONG, "بازار سرمایه": STRONG}),
    "auto": ("خودرو", {"خودرو": STRONG, "خودروسازان": STRONG, "ایران خودرو": STRONG, "سایپا": STRONG, "قیمت خودرو": STRONG, "بازار خودرو": STRONG}),
    "housing": ("مسکن", {"مسکن": STRONG, "اجاره": STRONG, "رهن": STRONG, "اجاره بها": STRONG, "ساخت و ساز": STRONG, "املاک": STRONG}),
    "commodities": ("کالاهای اساسی", {"کالاهای اساسی": STRONG, "کالای اساسی": STRONG, "مرغ": STRONG, "برنج": STRONG, "روغن": STRONG,
                                      "گوشت": STRONG, "نان": WEAK, "شیر": WEAK, "قیمت کالا": STRONG, "سبد کالا": STRONG, "کالابرگ": STRONG}),
    "crypto": ("رمزارز", {"بیت کوین": STRONG, "رمزارز": STRONG, "ارز دیجیتال": STRONG, "اتریوم": STRONG, "تتر": STRONG}),
    "macro": ("اقتصاد کلان", {"تورم": STRONG, "بودجه": STRONG, "نقدینگی": STRONG, "رشد اقتصادی": STRONG, "نفت": STRONG, "اقتصاد": STRONG,
                              "اقتصادی": STRONG, "مالیات": STRONG, "یارانه": STRONG, "صادرات": STRONG, "واردات": STRONG, "تجارت": WEAK,
                              "بانک": WEAK, "بازار": WEAK, "قیمت": WEAK, "معیشت": STRONG, "نرخ بهره": STRONG, "تحریم": WEAK,
                              "گاز": WEAK, "برق": WEAK, "بودجه ریزی": STRONG}),
}
CATEGORY_ORDER = ["currency", "gold", "stock", "auto", "housing", "commodities", "crypto", "macro"]

# Headlines about these topics are dropped unless they also contain a strong economic term.
OFF_TOPIC = {"فوتبال", "ورزشی", "بازیکن", "سینما", "فیلم", "سریال", "هنرمند", "جشنواره", "لیگ", "جام", "تیم ملی", "عزاداری",
             "سوگ", "عزا", "پیکر", "تشییع", "درگذشت", "حادثه", "تصادف", "زلزله", "آتش سوزی"}

STOPWORDS = {"و", "در", "به", "از", "که", "را", "با", "برای", "این", "آن", "است", "شد", "شده", "می", "یک", "تا", "هم", "بر", "یا",
             "ها", "های", "کرد", "کنند", "خواهد", "باید", "هر", "پس", "اما", "نیز", "بود", "دارد", "داد", "گفت"}

MAX_AGE = timedelta(days=7)
FUTURE_TOLERANCE = timedelta(minutes=10)
DEDUP_JACCARD = 0.6

_ZWNJ = "\u200c\u200d\u200e\u200f"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(text):
    text = (text or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه")
    for ch in _ZWNJ:
        text = text.replace(ch, " ")
    text = re.sub(r"[\u064b-\u065f\u0640]", "", text)        # harakat / tatweel
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def tokens(text):
    return normalize(text).split()


def _contains_phrase(norm_text, phrase):
    return re.search(r"(?<!\w)" + re.escape(normalize(phrase)) + r"(?!\w)", norm_text) is not None


def classify(title):
    """Return (category, relevance_score, matched_phrases). category None means: not an economic headline."""
    norm = normalize(title)
    per_cat, matched = {}, []
    for cat in CATEGORY_ORDER:
        score = 0
        for phrase, weight in CATEGORIES[cat][1].items():
            if _contains_phrase(norm, phrase):
                score += weight
                matched.append(phrase)
        per_cat[cat] = score
    total = sum(per_cat.values())
    strong_hit = any(
        _contains_phrase(norm, p) for c in CATEGORY_ORDER for p, w in CATEGORIES[c][1].items() if w == STRONG)
    if any(_contains_phrase(norm, w) for w in OFF_TOPIC) and not strong_hit:
        return None, 0, []
    if total < THRESHOLD:
        return None, total, matched
    best = max(CATEGORY_ORDER, key=lambda c: (per_cat[c], -CATEGORY_ORDER.index(c)))
    if per_cat[best] == 0:
        return None, total, matched
    return best, total, matched


def parse_date(raw, now=None):
    """Return (iso_utc_or_empty, status) with status in ok / missing / invalid / future / too_old."""
    now = now or datetime.now(timezone.utc)
    if not raw:
        return "", "missing"
    dt = None
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, (tuple, list)) and len(raw) >= 6:
        try:
            dt = datetime(*raw[:6], tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return "", "invalid"
    else:
        from email.utils import parsedate_to_datetime
        text = str(raw).strip()
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return "", "invalid"
    if dt is None:
        return "", "invalid"
    if dt.tzinfo is None:
        return "", "invalid"          # a clock time without a zone cannot be trusted
    dt = dt.astimezone(timezone.utc)
    if dt.year < 2000:
        return "", "invalid"
    if dt - now > FUTURE_TOLERANCE:
        return "", "future"
    if now - dt > MAX_AGE:
        return dt.isoformat(), "too_old"
    return dt.isoformat(), "ok"


def content_tokens(title):
    return {t for t in tokens(title) if t not in STOPWORDS and len(t) > 1}


def similarity(a, b):
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def dedupe(items):
    """Merge duplicates (same story from several outlets). Input must be sorted oldest-first priority is by
    list order: the first item of a group is kept and the others are listed in `also_reported_by`."""
    kept = []
    for item in items:
        for k in kept:
            same_url = item["url"] == k["url"]
            if same_url or similarity(item["title"], k["title"]) >= DEDUP_JACCARD:
                if item["source"] != k["source"] and item["source"] not in k.setdefault("also_reported_by", []):
                    k["also_reported_by"].append(item["source"])
                break
        else:
            kept.append(dict(item))
    return kept


def build_items(raw_items, now=None, limit=24):
    """raw_items: dicts with title, url, source, date (raw). Returns (items, stats)."""
    now = now or datetime.now(timezone.utc)
    stats = {"seen": 0, "off_topic": 0, "no_valid_date": 0, "too_old": 0, "duplicates": 0, "published": 0}
    ok = []
    for r in raw_items:
        stats["seen"] += 1
        title = re.sub(r"\s+", " ", (r.get("title") or "")).strip()
        url = (r.get("url") or "").strip()
        if not title or not url.startswith("https://"):
            continue
        cat, score, _ = classify(title)
        if not cat:
            stats["off_topic"] += 1
            continue
        iso, status = parse_date(r.get("date"), now)
        if status == "too_old":
            stats["too_old"] += 1
            continue
        if status != "ok":
            stats["no_valid_date"] += 1
            continue
        ok.append({"title": title, "url": url, "source": r.get("source", ""), "published_at": iso,
                   "category": cat, "category_label": CATEGORIES[cat][0], "relevance": score, "date_status": status})
    ok.sort(key=lambda x: (x["published_at"], x["relevance"]), reverse=True)
    deduped = dedupe(ok)
    stats["duplicates"] = len(ok) - len(deduped)
    final = deduped[:limit]
    stats["published"] = len(final)
    return final, stats
