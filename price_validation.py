"""Price quality control for Bazarnama (pure functions, no network, no file I/O).

Every price that reaches data/prices.json passes through `validate_items`. The goal is to keep a bad
reading out of the published files and out of the history WITHOUT treating a real market move as an error.

Decision for each priced item:
  accepted   - the reading is plausible (reason code says why)
  confirmed  - the reading was outside the normal band, but two consecutive runs agree, so it is a real move
  held       - outside the band and not yet confirmed: the last valid published value is kept (flagged stale)
  dropped    - rejected and there is no earlier valid value to keep: the price is not shown (never invented)
  skipped    - not checked (item already flagged stale, or no price)

A real move survives: a held reading becomes `confirmed` as soon as the next run reads (almost) the same
number. A one-off spike never reaches the site or the chart.
"""
import math

# Allowed distance (percent) beyond the 24-hour low/high seen in our own history, by family.
RANGE_TOLERANCE_PCT = {"currency": 8.0, "gold": 10.0, "coin": 10.0, "metal": 10.0, "crypto": 25.0, "energy": 15.0}
RANGE_TOLERANCE_DEFAULT = 15.0
MIN_POINTS_24H = 3                 # fewer own observations than this: no 24h band can be trusted
CONFIRM_PCT = 2.0                  # the next reading must agree with the held one within this band
PENDING_MAX_AGE = 3 * 3600         # a held reading older than this is forgotten
DISCREPANCY_REJECT_PCT = 25.0      # two independent sources this far apart: the pair is not trustworthy

REASONS = {
    "ok_in_range": "within the 24h band",
    "ok_no_baseline": "not enough own history for a 24h band; basic checks passed",
    "ok_confirmed_move": "outside the 24h band but confirmed by two consecutive readings",
    "held_outside_24h_range": "outside the 24h band; waiting for a confirming reading",
    "held_source_conflict": "independent sources disagree strongly; waiting for a confirming reading",
    "invalid_number": "price is missing, not a number, not finite or not positive",
    "skipped_stale": "item already flagged stale; not re-validated",
}


def tolerance(family):
    return RANGE_TOLERANCE_PCT.get(str(family or "").lower(), RANGE_TOLERANCE_DEFAULT)


def is_valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def range_24h(points, now):
    """(low, high, count) of the points observed in the last 24 hours, or None if there are too few."""
    vals = [float(p[1]) for p in points or [] if isinstance(p, (list, tuple)) and len(p) >= 2
            and is_valid_number(p[1]) and now - 86400 <= p[0] <= now]
    if len(vals) < MIN_POINTS_24H:
        return None
    return min(vals), max(vals), len(vals)


def check_range(price, band, family):
    """Return (in_band, detail). `band` is (low, high, n)."""
    low, high, n = band
    tol = tolerance(family) / 100.0
    lo, hi = low * (1 - tol), high * (1 + tol)
    return lo <= price <= hi, {"band_low": round(lo, 6), "band_high": round(hi, 6), "points_24h": n}


def validate_item(item, series, held, now):
    """Judge one item. Returns (decision, reason, detail, new_held).

    `series` - own history points [[epoch, price], ...] of this id; `held` - reading held by an earlier run
    ([epoch, price] or None). `new_held` is the reading to remember for the next run (or None).
    """
    price = item.get("price")
    if item.get("stale"):
        return "skipped", "skipped_stale", {}, None
    if not is_valid_number(price):
        return "dropped", "invalid_number", {}, None
    family = item.get("family")
    detail = {}
    suspicious = None
    band = range_24h(series, now)
    if band:
        ok, detail = check_range(float(price), band, family)
        if not ok:
            suspicious = "held_outside_24h_range"
    secondary = item.get("secondary_price") if is_valid_number(item.get("secondary_price")) else None
    if secondary and not suspicious:
        gap = abs(float(price) / float(secondary) - 1) * 100
        detail["source_gap_pct"] = round(gap, 3)
        if gap > DISCREPANCY_REJECT_PCT:
            suspicious = "held_source_conflict"
    if not suspicious:
        return "accepted", ("ok_in_range" if band else "ok_no_baseline"), detail, None
    if held and now - held[0] <= PENDING_MAX_AGE and is_valid_number(held[1]) \
            and abs(float(price) / float(held[1]) - 1) * 100 <= CONFIRM_PCT:
        detail["confirmed_against"] = held[1]
        return "confirmed", "ok_confirmed_move", detail, None
    return "held", suspicious, detail, [now, float(price)]


def validate_items(items, previous_items, series_by_id, pending, now):
    """Apply `validate_item` to every item in place.

    previous_items - items of the last published prices.json (source of the last valid value)
    series_by_id   - own history series per id;  pending - {id: [epoch, price]} held readings from earlier runs
    Returns (log_entries, new_pending). Items that are held are replaced by the last valid published item
    (flagged stale); items that are dropped are removed from `items`.
    """
    prev = {i.get("id"): i for i in previous_items or [] if isinstance(i, dict)}
    log, new_pending, drop = [], {}, []
    for idx, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        pid = item["id"]
        decision, reason, detail, new_held = validate_item(item, series_by_id.get(pid), (pending or {}).get(pid), now)
        entry = {"id": pid, "decision": decision, "reason": reason, "price": item.get("price")}
        entry.update(detail)
        if decision == "held":
            last = prev.get(pid)
            if last and is_valid_number(last.get("price")) and not (last.get("validation") or {}).get("status") == "dropped":
                entry["kept_price"] = last["price"]
                kept = dict(last)
                kept["stale"] = True
                items[idx] = kept
                item = kept
            else:
                entry["decision"], decision = "dropped", "dropped"
                drop.append(idx)
        elif decision == "dropped":
            drop.append(idx)
        if new_held:
            new_pending[pid] = new_held
        if decision != "skipped" and idx not in drop:
            item["validation"] = {"status": decision, "reason": reason}
        log.append(entry)
    for idx in sorted(drop, reverse=True):
        del items[idx]
    return log, new_pending


def summarize(log):
    counts = {}
    for e in log:
        counts[e["decision"]] = counts.get(e["decision"], 0) + 1
    return counts
