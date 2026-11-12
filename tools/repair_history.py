#!/usr/bin/env python3
"""Find and (optionally) remove isolated one-point spikes from the price history.

A point is an isolated spike only if ALL of these hold:
  - its neighbours are at most 6 hours away on both sides,
  - the neighbours agree with each other within 3 %,
  - the point differs from both neighbours by more than the family jump limit (same limits as update_prices).
Real market moves (a level change that persists) are never touched.

Default is a dry run. With --apply the points are removed from data/history-archive.json and
data/history.json, and every removed point is recorded in data/history-repairs.json (nothing is lost silently).
"""
import datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIMIT = {"currency": 8.0, "gold": 10.0, "coin": 10.0, "metal": 10.0, "crypto": 25.0, "energy": 15.0}
DEFAULT = 15.0
NEIGHBOUR_AGREE_PCT = 3.0
MAX_GAP = 6 * 3600


def pct(a, b):
    return abs(a / b - 1) * 100


def find_spikes(points, limit):
    out = []
    for i in range(1, len(points) - 1):
        (t0, p0), (t1, p1), (t2, p2) = points[i - 1][:2], points[i][:2], points[i + 1][:2]
        if t1 - t0 > MAX_GAP or t2 - t1 > MAX_GAP or not (p0 and p1 and p2):
            continue
        if pct(p2, p0) <= NEIGHBOUR_AGREE_PCT and pct(p1, p0) > limit and pct(p1, p2) > limit:
            out.append(points[i])
    return out


def families():
    prices = json.loads((ROOT / "data" / "prices.json").read_text(encoding="utf-8"))
    return {i["id"]: i.get("family") for i in prices.get("items", []) if isinstance(i, dict) and i.get("id")}


def main(apply):
    fam = families()
    archive_p, lean_p = ROOT / "data" / "history-archive.json", ROOT / "data" / "history.json"
    archive = json.loads(archive_p.read_text(encoding="utf-8"))
    removed = []
    for pid, pts in archive["series"].items():
        for bad in find_spikes(pts, LIMIT.get(str(fam.get(pid) or "").lower(), DEFAULT)):
            removed.append({"id": pid, "t": bad[0], "price": bad[1]})
            print(f"spike: {pid} t={bad[0]} price={bad[1]}")
    print(f"{len(removed)} isolated spike(s) found")
    if not (apply and removed):
        return len(removed)
    drop = {(r["id"], r["t"]) for r in removed}
    for path in (archive_p, lean_p):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for pid, pts in doc["series"].items():
            doc["series"][pid] = [p for p in pts if (pid, p[0]) not in drop]
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log_p = ROOT / "data" / "history-repairs.json"
    log = json.loads(log_p.read_text(encoding="utf-8")) if log_p.exists() else {"repairs": []}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log["repairs"].extend({**r, "removed_utc": stamp, "reason": "isolated spike between two agreeing neighbours"} for r in removed)
    log_p.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("removed and logged in data/history-repairs.json")
    return len(removed)


if __name__ == "__main__":
    main("--apply" in sys.argv)
