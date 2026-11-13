#!/usr/bin/env python3
"""Record the outcome of an automatic update run in data/run-report.json.

Usage: python3 tools/record_run.py success|failure ["reason"]
Only real outcomes are written: last_success_utc changes on success, last_failure_utc on failure.
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "data" / "run-report.json"
KEEP = 20


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(status, reason="", path=REPORT, now=None):
    if status not in ("success", "failure"):
        raise ValueError("status must be success or failure")
    now = now or now_iso()
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            doc = {}
    except (OSError, ValueError):
        doc = {}
    runs = [r for r in doc.get("runs", []) if isinstance(r, dict)]
    runs.append({"utc": now, "status": status, "reason": str(reason)[:300]})
    doc.update({"schema": "bazarnama/run-report/v1", "last_status": status, "last_run_utc": now,
                "runs": runs[-KEEP:]})
    doc["last_success_utc" if status == "success" else "last_failure_utc"] = now
    doc.setdefault("last_success_utc", None)
    doc.setdefault("last_failure_utc", None)
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
    return doc


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: record_run.py success|failure [reason]")
    record(sys.argv[1], " ".join(sys.argv[2:]))
