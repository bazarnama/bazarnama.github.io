import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_prices", ROOT / "update_prices.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FreshnessTests(unittest.TestCase):
    def test_provider_timestamp_is_used_not_fetch_time(self):
        item = {"id": "btc", "family": "crypto", "updated_utc": "2026-11-09T12:00:00Z"}
        epoch = module.item_source_epoch(item)
        self.assertIsNotNone(epoch)
        self.assertEqual(module.datetime.datetime.fromtimestamp(epoch, module.datetime.timezone.utc).isoformat(), "2026-11-09T12:00:00+00:00")

    def test_missing_timestamp_is_unknown(self):
        health = module.annotate_freshness([{"id": "btc", "family": "crypto", "price": 1}], checked_at=1794225600)
        self.assertEqual(health["counts"]["unknown"], 1)

    def test_old_crypto_is_marked_stale(self):
        item = {"id": "btc", "family": "crypto", "updated_utc": "2026-11-09T00:00:00Z", "price": 1}
        checked = module.parse_timestamp("2026-11-09T01:00:00Z")
        health = module.annotate_freshness([item], checked_at=checked)
        self.assertTrue(item["stale"])
        self.assertEqual(item["freshness"]["status"], "stale")
        self.assertEqual(health["counts"]["stale"], 1)

    def test_provider_stale_flag_is_preserved(self):
        item = {"id": "opec-basket", "family": "energy", "updated_utc": "2026-11-08T20:00:00Z", "price": 1, "stale": True}
        checked = module.parse_timestamp("2026-11-09T01:00:00Z")
        health = module.annotate_freshness([item], checked_at=checked)
        self.assertEqual(item["freshness"]["status"], "stale")
        self.assertEqual(health["counts"]["stale"], 1)

    def test_fresh_crypto_remains_fresh(self):
        item = {"id": "btc", "family": "crypto", "updated_utc": "2026-11-09T12:00:00Z", "price": 1}
        checked = module.parse_timestamp("2026-11-09T12:05:00Z")
        health = module.annotate_freshness([item], checked_at=checked)
        self.assertEqual(item["freshness"]["status"], "fresh")
        self.assertFalse(item.get("stale", False))

    def test_provider_clock_far_in_future_is_unknown(self):
        item = {"id": "btc", "family": "crypto", "updated_utc": "2026-11-09T12:20:00Z", "price": 1}
        checked = module.parse_timestamp("2026-11-09T12:00:00Z")
        health = module.annotate_freshness([item], checked_at=checked)
        self.assertEqual(item["freshness"]["status"], "unknown")
        self.assertEqual(health["counts"]["unknown"], 1)

    def test_stale_quote_is_not_revalidated_by_fetch_time(self):
        item = {"id": "btc", "family": "crypto", "updated_utc": "2026-11-09T11:00:00Z", "fetched_utc": "2026-11-09T12:00:00Z", "price": 1}
        checked = module.parse_timestamp("2026-11-09T12:00:00Z")
        health = module.annotate_freshness([item], checked_at=checked)
        self.assertEqual(item["freshness"]["status"], "stale")
        self.assertEqual(item["freshness"]["observed_utc"], "2026-11-09T11:00:00Z")


if __name__ == "__main__":
    unittest.main()
