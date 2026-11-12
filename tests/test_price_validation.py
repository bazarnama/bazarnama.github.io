import importlib.util, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("price_validation", ROOT / "price_validation.py")
pv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pv)

NOW = 1_800_000_000
H = 3600


def series(value, n=6):
    return [[NOW - i * H, value] for i in range(n, 0, -1)]


class ValidateItemTests(unittest.TestCase):
    def test_normal_price_is_accepted(self):
        d, r, _, held = pv.validate_item({"id": "usd", "family": "currency", "price": 101.0}, series(100.0), None, NOW)
        self.assertEqual((d, r, held), ("accepted", "ok_in_range", None))

    def test_real_daily_move_inside_band_is_not_an_error(self):
        pts = [[NOW - 5 * H, 100.0], [NOW - 3 * H, 104.0], [NOW - 1 * H, 108.0]]
        self.assertEqual(pv.validate_item({"id": "usd", "family": "currency", "price": 111.0}, pts, None, NOW)[0], "accepted")

    def test_spike_outside_band_is_held(self):
        d, r, _, held = pv.validate_item({"id": "xau", "family": "metal", "price": 150.0}, series(100.0), None, NOW)
        self.assertEqual((d, r), ("held", "held_outside_24h_range"))
        self.assertEqual(held, [NOW, 150.0])

    def test_two_agreeing_readings_confirm_a_real_move(self):
        d, r, _, held = pv.validate_item({"id": "xau", "family": "metal", "price": 150.5}, series(100.0), [NOW - 600, 150.0], NOW)
        self.assertEqual((d, r, held), ("confirmed", "ok_confirmed_move", None))

    def test_old_held_reading_is_not_used_to_confirm(self):
        d, *_ = pv.validate_item({"id": "xau", "family": "metal", "price": 150.0}, series(100.0), [NOW - 5 * H, 150.0], NOW)
        self.assertEqual(d, "held")

    def test_not_enough_history_means_no_band(self):
        d, r, *_ = pv.validate_item({"id": "usd", "family": "currency", "price": 500.0}, series(100.0, n=2), None, NOW)
        self.assertEqual((d, r), ("accepted", "ok_no_baseline"))

    def test_invalid_numbers_are_dropped(self):
        for bad in (None, 0, -5, float("nan"), float("inf"), "12", True):
            self.assertEqual(pv.validate_item({"id": "usd", "price": bad}, series(100.0), None, NOW)[0], "dropped", bad)

    def test_stale_item_is_skipped(self):
        self.assertEqual(pv.validate_item({"id": "usd", "price": 1, "stale": True}, [], None, NOW)[0], "skipped")

    def test_independent_sources_far_apart_are_held(self):
        d, r, *_ = pv.validate_item({"id": "eur", "family": "currency", "price": 100.0, "secondary_price": 60.0}, series(100.0), None, NOW)
        self.assertEqual((d, r), ("held", "held_source_conflict"))

    def test_crypto_has_a_wider_band(self):
        self.assertEqual(pv.validate_item({"id": "btc", "family": "crypto", "price": 120.0}, series(100.0), None, NOW)[0], "accepted")


class ValidateItemsTests(unittest.TestCase):
    def test_held_item_keeps_last_valid_price_and_is_flagged_stale(self):
        items = [{"id": "xau", "family": "metal", "price": 150.0}]
        prev = [{"id": "xau", "family": "metal", "price": 100.0, "updated_utc": "2026-01-01T00:00:00Z"}]
        log, pend = pv.validate_items(items, prev, {"xau": series(100.0)}, {}, NOW)
        self.assertEqual(items[0]["price"], 100.0)
        self.assertTrue(items[0]["stale"])
        self.assertEqual(items[0]["validation"]["status"], "held")
        self.assertEqual(log[0]["kept_price"], 100.0)
        self.assertIn("xau", pend)

    def test_held_item_without_previous_value_is_dropped_not_invented(self):
        items = [{"id": "xau", "family": "metal", "price": 150.0}, {"id": "usd", "family": "currency", "price": 100.0}]
        log, _ = pv.validate_items(items, [], {"xau": series(100.0), "usd": series(100.0)}, {}, NOW)
        self.assertEqual([i["id"] for i in items], ["usd"])
        self.assertEqual(log[0]["decision"], "dropped")

    def test_accepted_item_is_not_modified_except_validation_flag(self):
        items = [{"id": "usd", "family": "currency", "price": 101.0}]
        pv.validate_items(items, [], {"usd": series(100.0)}, {}, NOW)
        self.assertEqual(items[0]["price"], 101.0)
        self.assertEqual(items[0]["validation"], {"status": "accepted", "reason": "ok_in_range"})

    def test_summary_counts(self):
        self.assertEqual(pv.summarize([{"decision": "accepted"}, {"decision": "held"}, {"decision": "accepted"}]), {"accepted": 2, "held": 1})


if __name__ == "__main__":
    unittest.main()
