import importlib.util, pathlib, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_prices", ROOT / "update_prices.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

H = 3600


class JumpScreeningTests(unittest.TestCase):
    def test_normal_move_is_appended(self):
        pts, pend = [[0, 100.0]], {}
        self.assertEqual(m.screen_point(pts, pend, "usd", H, 102.0, "currency"), [[H, 102.0]])
        self.assertEqual(pend, {})

    def test_one_off_spike_is_held_not_recorded(self):
        pts, pend = [[0, 100.0]], {}
        self.assertEqual(m.screen_point(pts, pend, "silver", H, 80.0, "metal"), [])
        self.assertIn("silver", pend)

    def test_spike_followed_by_normal_price_is_dropped(self):
        pts, pend = [[0, 100.0]], {}
        m.screen_point(pts, pend, "silver", H, 80.0, "metal")
        self.assertEqual(m.screen_point(pts, pend, "silver", 2 * H, 100.5, "metal"), [[2 * H, 100.5]])
        self.assertNotIn("silver", pend)

    def test_confirmed_move_is_recorded(self):
        pts, pend = [[0, 100.0]], {}
        m.screen_point(pts, pend, "silver", H, 80.0, "metal")
        out = m.screen_point(pts, pend, "silver", 2 * H, 80.4, "metal")
        self.assertEqual([p[1] for p in out], [80.0, 80.4])

    def test_large_move_after_long_gap_is_accepted(self):
        pts, pend = [[0, 100.0]], {}
        self.assertEqual(m.screen_point(pts, pend, "usd", 12 * H, 130.0, "currency"), [[12 * H, 130.0]])

    def test_crypto_has_wider_limit(self):
        pts, pend = [[0, 100.0]], {}
        self.assertEqual(len(m.screen_point(pts, pend, "btc", H, 115.0, "crypto")), 1)


class DailySeriesFreshnessTests(unittest.TestCase):
    def test_daily_spot_not_stale_after_weekend(self):
        item = {"id": "brent-spot", "family": "energy", "updated_utc": "2026-11-06T00:00:00Z", "price": 1}
        checked = m.parse_timestamp("2026-11-09T06:00:00Z")   # ~3.25 days later
        m.annotate_freshness([item], checked_at=checked)
        self.assertNotEqual(item["freshness"]["status"], "stale")

    def test_daily_spot_really_old_is_stale(self):
        item = {"id": "wti-spot", "family": "energy", "updated_utc": "2026-11-04T00:00:00Z", "price": 1}
        m.annotate_freshness([item], checked_at=m.parse_timestamp("2026-11-12T00:00:00Z"))
        self.assertEqual(item["freshness"]["status"], "stale")

    def test_intraday_energy_still_uses_two_hours(self):
        item = {"id": "brent", "family": "energy", "updated_utc": "2026-11-09T00:00:00Z", "price": 1}
        m.annotate_freshness([item], checked_at=m.parse_timestamp("2026-11-09T03:00:00Z"))
        self.assertEqual(item["freshness"]["status"], "stale")


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_replaces_file_and_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.json"
            p.write_text("old", encoding="utf-8")
            self.assertTrue(m.write_if_changed(p, "new"))
            self.assertEqual(p.read_text(encoding="utf-8"), "new")
            self.assertEqual([f.name for f in pathlib.Path(d).iterdir()], ["x.json"])
            self.assertFalse(m.write_if_changed(p, "new"))


if __name__ == "__main__":
    unittest.main()
