#!/usr/bin/env python3
"""Read-only report of suspicious points in data/history-archive.json. Never modifies any file."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
LIMIT = {"usd": 8, "eur": 8, "gbp": 8, "aed": 8}   # percent per step within 6h; others use 15
data = json.loads((ROOT / "data" / "history-archive.json").read_text(encoding="utf-8"))["series"]
found = 0
for pid, pts in sorted(data.items()):
    for a, b in zip(pts, pts[1:]):
        if a[1] and b[0] - a[0] <= 6 * 3600:
            pct = abs(b[1] / a[1] - 1) * 100
            if pct > LIMIT.get(pid, 15):
                found += 1
                print(f"{pid}: {a[0]}={a[1]} -> {b[0]}={b[1]}  ({pct:.1f}%)")
print(f"{found} suspicious step(s)", file=sys.stderr)
