import importlib.util
import pathlib
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_prices", ROOT / "update_prices.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


class DirectMarketSourceTests(unittest.TestCase):
    def test_own_dollar_derived_prices_are_removed(self):
        items = [
            {"id": "usd", "price": 100, "method": "average"},
            {"id": "eur", "price": 120, "derived": True, "derived_from": "usd"},
            {"id": "xyz", "price": 5, "method": "derived"},
        ]
        removed = module.drop_derived(items)
        self.assertEqual(sorted(removed), ["eur", "xyz"])
        self.assertEqual([x["id"] for x in items], ["usd"])

    def test_nerkhara_method_derived_is_kept_for_main_currencies(self):
        items = [{"id": "eur", "price": 120, "method": "derived"}, {"id": "cny", "price": 40, "method": "derived"}]
        self.assertEqual(module.drop_derived(items), [])
        self.assertEqual([x["id"] for x in items], ["eur", "cny"])

    def test_independent_source_selection_ignores_stale_quotes(self):
        chosen = module.choose_independent([
            {"price": 300000, "source_name": "stale", "stale": True},
            {"price": 301000, "source_name": "fresh", "stale": False},
        ])
        self.assertEqual(chosen["source_name"], "fresh")

    def test_nerkhara_eur_stays_first_source_even_if_method_derived(self):
        items = [{"id": "eur", "price": 300000, "method": "derived", "unit": "IRT", "source_name": "NerkhAra",
                  "source_updated_utc": "2026-11-11T13:30:00Z"}]
        direct = {"eur": {"price": 305000, "unit": "IRT", "method": "direct",
                          "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T13:40:00Z", "stale": False}}
        module.select_currency_quotes(items, direct)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 300000)
        self.assertEqual(items[0]["source_name"], "NerkhAra")

    def test_fresh_direct_quote_fills_in_when_primary_is_our_own_estimate(self):
        items = [{"id": "eur", "price": 120, "derived": True, "unit": "IRT"}]
        direct = {"eur": {"price": 305000, "unit": "IRT", "method": "direct",
                          "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T13:40:00Z", "stale": False}}
        module.select_currency_quotes(items, direct)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 305000)

    def test_own_estimate_without_backup_is_removed(self):
        items = [{"id": "eur", "price": 120, "derived": True, "unit": "IRT"}]
        module.select_currency_quotes(items, {})
        self.assertEqual(items, [])

    def test_extra_currency_prefers_nerkhara(self):
        items = [{"id": "cny", "price": 39500, "method": "derived", "unit": "IRT", "source_name": "NerkhAra"}]
        ns = {"cny": {"price": 39600, "unit": "IRT", "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T13:40:00Z"}}
        module.add_extra_currencies(items, ns)
        self.assertEqual(items[0]["price"], 39500)
        self.assertEqual(items[0]["source_name"], "NerkhAra")

    def test_extra_currency_falls_back_to_nerkhsanj(self):
        items = []
        ns = {"cny": {"price": 39600, "unit": "IRT", "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T13:40:00Z"}}
        module.add_extra_currencies(items, ns)
        self.assertEqual(items[0]["price"], 39600)

    def test_newer_direct_backup_does_not_replace_fresh_primary(self):
        items = [{"id": "usd", "price": 263000, "method": "average", "unit": "IRT",
                  "source_updated_utc": "2026-11-09T13:30:00Z", "source_name": "NerkhAra"}]
        validation = {"usd": {"price": 263500, "unit": "IRT", "method": "direct",
                              "source_name": "NerkhSanj", "source_updated_utc": "2026-11-09T13:40:00Z"}}
        module.select_currency_quotes(items, validation)
        self.assertEqual(items[0]["source_name"], "NerkhAra")
        self.assertEqual(items[0]["price"], 263000)
        self.assertEqual(items[0]["validation_source"], "NerkhSanj")


    def test_large_source_disagreement_keeps_primary_and_flags_warning(self):
        items = [{"id": "usd", "price": 263000, "method": "average", "unit": "IRT",
                  "source_updated_utc": "2026-11-09T13:30:00Z", "source_name": "NerkhAra"}]
        backup = {"usd": {"price": 300000, "unit": "IRT", "method": "direct",
                          "source_name": "NerkhSanj", "source_updated_utc": "2026-11-09T13:40:00Z"}}
        module.select_currency_quotes(items, backup)
        self.assertEqual(items[0]["source_name"], "NerkhAra")
        self.assertTrue(items[0]["validation_warning"])

    def test_fred_daily_energy_csv_is_parsed_without_api_key(self):
        def fake_urlopen(request, timeout=20):
            query = parse_qs(urlparse(request.full_url).query)
            series = query["id"][0]
            body = f"observation_date,{series}\n2026-11-06,90.0\n2026-11-09,92.0\n"
            return FakeResponse(body)
        with patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = module.fetch_fred_energy()
        self.assertEqual(set(result), {"brent-spot", "wti-spot", "natural-gas"})
        self.assertEqual(result["brent-spot"]["price"], 92.0)
        self.assertEqual(result["brent-spot"]["backup_source"], "fred")
        self.assertEqual(result["brent-spot"]["market_type"], "daily-spot")
        self.assertAlmostEqual(result["brent-spot"]["change_pct"], 2.2222, places=3)
        self.assertEqual(len(result["brent-spot"]["_history_points"]), 2)

    def test_nerkhsanj_direct_quotes_keep_provider_timestamp_and_toman_unit(self):
        payload = {
            "date": "1405/08/18", "time": "17:10",
            "rates": {"dollar": 263900, "euro": 305000, "pound": 350000, "aed": 71800, "tether": 264100, "yuan": 39500},
            "change": {"dollar": 0.2, "euro": -0.1},
        }
        with patch.object(module, "get_json", return_value=payload):
            result = module.fetch_nerkhsanj()
        self.assertEqual(result["usd"]["source_name"], "NerkhSanj")
        self.assertEqual(result["usd"]["unit"], "IRT")
        self.assertEqual(result["usd"]["method"], "direct")
        self.assertEqual(result["usd"]["change_pct"], 0.2)
        self.assertEqual(result["cny"]["price"], 39500)
        self.assertTrue(result["usd"]["source_updated_utc"].endswith("Z"))

    def test_explicit_rial_unit_is_normalized_without_ratio_guessing(self):
        row = {"price": 2630000, "unit": "IRR"}
        normalized = module.normalize_local_currency_unit(row)
        self.assertEqual(normalized["price"], 263000)
        self.assertEqual(normalized["unit"], "IRT")
        self.assertEqual(normalized["unit_normalization"], "IRR_to_IRT_divide_by_10")
        self.assertIsNone(module.normalize_local_currency_unit({"price": 263000, "unit": ""}))

    def test_usdt_quoted_assets_do_not_expose_derived_toman_field(self):
        items = [{"id": "btc", "price": 90000, "unit": "USDT", "price_irt": 900000000, "method": "lead"}]
        module.drop_derived(items)
        self.assertNotIn("price_irt", items[0])


if __name__ == "__main__":
    unittest.main()
