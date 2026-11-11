import importlib.util
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_prices", ROOT / "update_prices.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

JALALI_DATE = "1405/08/18"
CLOCK = "17:10"


def secondary(price, name="NerkhSanj"):
    return {"price": price, "unit": "IRT", "method": "direct", "source_name": name,
            "source_updated_utc": "2026-11-09T13:40:00Z"}


class DropDerivedTests(unittest.TestCase):
    def test_our_own_derived_rows_are_removed_but_flagged_usdt_is_kept(self):
        items = [
            {"id": "usd", "price": 100, "method": "average"},
            {"id": "gbp", "price": 130, "derived": True},
            {"id": "usdt", "price": 100, "derived": True},
        ]
        removed = module.drop_derived(items)
        self.assertEqual(removed, ["gbp"])
        self.assertEqual([i["id"] for i in items], ["usd", "usdt"])

    def test_primary_derived_rows_survive_only_for_kept_ids(self):
        items = [
            {"id": "eur", "price": 120, "method": "derived"},   # NerkhAra is the first source for eur
            {"id": "cny", "price": 40, "method": "derived"},    # not in KEEP_FROM_PRIMARY
        ]
        removed = module.drop_derived(items)
        self.assertEqual(removed, ["cny"])
        self.assertEqual([i["id"] for i in items], ["eur"])


class SelectCurrencyQuotesTests(unittest.TestCase):
    def test_derived_primary_is_replaced_by_direct_secondary_quote(self):
        items = [{"id": "eur", "price": 120, "derived": True, "unit": "IRT"}]
        module.select_currency_quotes(items, {"eur": secondary(305000)})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 305000)
        self.assertEqual(items[0]["source_selection"], "secondary-direct")

    def test_derived_primary_without_secondary_is_not_published(self):
        items = [{"id": "eur", "price": 120, "derived": True, "unit": "IRT"}]
        module.select_currency_quotes(items, {})
        self.assertEqual(items, [])

    def test_agreeing_secondary_keeps_primary_and_records_check(self):
        items = [{"id": "usd", "price": 263000, "unit": "IRT", "source_name": "NerkhAra",
                  "updated_utc": "2026-11-09T13:30:00Z"}]
        checks = module.select_currency_quotes(items, {"usd": secondary(263500)})
        self.assertEqual(items[0]["price"], 263000)
        self.assertEqual(items[0]["source_name"], "NerkhAra")
        self.assertEqual(items[0]["source_selection"], "primary-aggregated")
        self.assertEqual(items[0]["secondary_source"], "NerkhSanj")
        self.assertFalse(items[0]["discrepancy_warning"])
        self.assertTrue(checks["usd"]["secondary_available"])

    def test_large_disagreement_keeps_primary_and_flags_warning(self):
        items = [{"id": "usd", "price": 263000, "unit": "IRT", "source_name": "NerkhAra",
                  "updated_utc": "2026-11-09T13:30:00Z"}]
        module.select_currency_quotes(items, {"usd": secondary(300000)})
        self.assertEqual(items[0]["price"], 263000)
        self.assertEqual(items[0]["source_name"], "NerkhAra")
        self.assertTrue(items[0]["discrepancy_warning"])

    def test_stale_primary_without_secondary_stays_marked_stale(self):
        items = [{"id": "usd", "price": 263000, "unit": "IRT", "stale": True,
                  "updated_utc": "2026-11-01T00:00:00Z"}]
        module.select_currency_quotes(items, {})
        self.assertTrue(items[0]["stale"])
        self.assertEqual(items[0]["price"], 263000)


class ChooseIndependentTests(unittest.TestCase):
    def q(self, price, name):
        return {"price": price, "source_name": name}

    def test_no_usable_quote_returns_none(self):
        self.assertIsNone(module.choose_independent([]))
        self.assertIsNone(module.choose_independent([None, {"price": 0, "source_name": "x"}]))

    def test_two_agreeing_quotes_are_both_counted(self):
        chosen = module.choose_independent([self.q(100, "A"), self.q(101, "B")])
        self.assertEqual(chosen["price"], 100)
        self.assertEqual(chosen["sources"], 2)
        self.assertFalse(chosen["discrepancy_warning"])

    def test_two_disagreeing_quotes_keep_the_first_and_warn(self):
        chosen = module.choose_independent([self.q(100, "A"), self.q(150, "B")])
        self.assertEqual(chosen["price"], 100)
        self.assertEqual(chosen["sources"], 1)
        self.assertTrue(chosen["discrepancy_warning"])

    def test_three_quotes_drop_the_outlier(self):
        chosen = module.choose_independent([self.q(100, "A"), self.q(101, "B"), self.q(150, "C")])
        self.assertEqual(chosen["price"], 100)
        self.assertEqual(chosen["sources"], 2)
        self.assertTrue(chosen["discrepancy_warning"])


class PreferDirectUsdtTests(unittest.TestCase):
    def test_direct_tether_quote_replaces_copy_of_dollar_price(self):
        items = [{"id": "usdt", "price": 263000, "derived": True}]
        module.prefer_direct_usdt(items, {"usdt": secondary(264100)})
        self.assertEqual(items[0]["price"], 264100)
        self.assertEqual(items[0]["source_selection"], "direct-single")

    def test_fresh_primary_tether_is_kept(self):
        items = [{"id": "usdt", "price": 264000, "method": "average"}]
        module.prefer_direct_usdt(items, {"usdt": secondary(264100)})
        self.assertEqual(items[0]["price"], 264000)


class FetchNerkhSanjTests(unittest.TestCase):
    PAYLOAD = {"date": JALALI_DATE, "time": CLOCK,
               "rates": {"dollar": 263900, "euro": 305000, "aed": 71800, "tether": 264100, "yuan": 39500}}

    def stamp(self):
        return module.jalali_text_to_tehran_epoch(JALALI_DATE, CLOCK)

    def test_fresh_quotes_keep_provider_timestamp_and_toman_unit(self):
        with patch.object(module, "get_json", return_value=self.PAYLOAD), \
             patch.object(module.time, "time", return_value=self.stamp() + 600):
            result = module.fetch_nerkhsanj()
        self.assertEqual(result["usd"]["price"], 263900)
        self.assertEqual(result["usd"]["unit"], "IRT")
        self.assertEqual(result["usd"]["source_name"], "NerkhSanj")
        self.assertEqual(result["usd"]["method"], "direct")
        self.assertEqual(result["cny"]["price"], 39500)
        self.assertTrue(result["usd"]["source_updated_utc"].endswith("Z"))
        self.assertFalse(result["usd"]["market_closed"])

    def test_quote_older_than_three_hours_is_rejected(self):
        with patch.object(module, "get_json", return_value=self.PAYLOAD), \
             patch.object(module.time, "time", return_value=self.stamp() + 4 * 3600):
            self.assertEqual(module.fetch_nerkhsanj(), {})

    def test_closed_market_quote_is_accepted_but_flagged_closed(self):
        payload = dict(self.PAYLOAD, time="")
        with patch.object(module, "get_json", return_value=payload), \
             patch.object(module.time, "time", return_value=self.stamp() + 30 * 3600):
            result = module.fetch_nerkhsanj()
        self.assertTrue(result["usd"]["market_closed"])

    def test_malformed_response_returns_empty(self):
        with patch.object(module, "get_json", return_value={"unexpected": True}):
            self.assertEqual(module.fetch_nerkhsanj(), {})


class FetchEiaTests(unittest.TestCase):
    ROWS = {"response": {"data": [{"period": "2026-11-09", "value": "92.0"},
                                  {"period": "2026-11-06", "value": "90.0"}]}}

    def test_without_api_key_nothing_is_fetched(self):
        with patch.dict(module.os.environ, {"EIA_API_KEY": ""}), \
             patch.object(module, "get_json", side_effect=AssertionError("must not be called")):
            self.assertEqual(module.fetch_eia(), {})

    def test_with_api_key_latest_value_and_change_are_parsed(self):
        with patch.dict(module.os.environ, {"EIA_API_KEY": "test-key"}), \
             patch.object(module, "get_json", return_value=self.ROWS):
            result = module.fetch_eia()
        self.assertEqual(set(result), {pid for pid, *_ in module.EIA_SERIES})
        self.assertEqual(result["brent"]["price"], 92.0)
        self.assertEqual(result["brent"]["source"], "EIA")
        self.assertAlmostEqual(result["brent"]["change_pct"], 2.2222, places=3)


if __name__ == "__main__":
    unittest.main()
