import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import record_run  # noqa: E402


class RecordRunTests(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "run-report.json"

    def test_success_and_failure_are_tracked_separately(self):
        d = record_run.record("success", path=self.path, now="2026-01-01T00:00:00Z")
        self.assertEqual(d["last_success_utc"], "2026-01-01T00:00:00Z")
        self.assertIsNone(d["last_failure_utc"])
        d = record_run.record("failure", "push failed", path=self.path, now="2026-01-01T00:05:00Z")
        self.assertEqual(d["last_success_utc"], "2026-01-01T00:00:00Z")
        self.assertEqual(d["last_failure_utc"], "2026-01-01T00:05:00Z")
        self.assertEqual(d["last_status"], "failure")

    def test_history_is_capped(self):
        for i in range(30):
            d = record_run.record("success", path=self.path, now=f"2026-01-01T00:{i:02d}:00Z")
        self.assertEqual(len(d["runs"]), record_run.KEEP)

    def test_bad_status_and_corrupt_file(self):
        with self.assertRaises(ValueError):
            record_run.record("ok", path=self.path)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(record_run.record("success", path=self.path)["last_status"], "success")


if __name__ == "__main__":
    unittest.main()
