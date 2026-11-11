import importlib.util
import pathlib
import unittest
from unittest.mock import patch

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
    def test_method_derived_is_removed_from_public_market_items(self):
        items = [
            {"id": "usd", "price": 100, "method": "average"},
            {"id": "eur", "price": 120, "method": "derived"},
            {"id": "gbp", "price": 130, "derived": True},
        ]
        removed = module.drop_derived(items)
        self.assertEqual(set(removed), {"eur", "gbp"})
        self.assertEqual([x["id"] for x in items], ["usd"])

    def test_direct_secondary_replaces_derived_primary(self):
        items = [{"id": "eur", "price": 120, "method": "derived", "unit": "IRT"}]
        direct = {"eur": {"price": 305000, "unit": "IRT", "method": "direct",
                          "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T10:00:00Z"}}
        module.select_currency_quotes(items, direct)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["price"], 305000)
        self.assertEqual(items[0]["source_selection"], "secondary-direct")

    def test_derived_currency_is_removed_when_no_direct_quote_exists(self):
        items = [{"id": "eur", "price": 120, "method": "derived", "unit": "IRT"}]
        module.select_currency_quotes(items, {})
        self.assertEqual(items, [])

    def test_direct_primary_is_kept_and_secondary_is_validation_only(self):
        items = [{"id": "usd", "price": 263000, "method": "average", "unit": "IRT",
                  "source_updated_utc": "2026-11-11T10:00:00Z", "source_name": "NerkhAra"}]
        direct = {"usd": {"price": 263500, "unit": "IRT", "method": "direct",
                          "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T10:05:00Z"}}
        module.select_currency_quotes(items, direct)
        self.assertEqual(items[0]["source_name"], "NerkhAra")
        self.assertEqual(items[0]["price"], 263000)
        self.assertEqual(items[0]["secondary_source"], "NerkhSanj")

    def test_direct_tether_replaces_method_derived_tether(self):
        items = [{"id": "usdt", "price": 263000, "method": "derived", "unit": "IRT"}]
        direct = {"usdt": {"price": 264000, "unit": "IRT", "method": "direct",
                           "source_name": "NerkhSanj", "source_updated_utc": "2026-11-11T10:00:00Z"}}
        module.prefer_direct_usdt(items, direct)
        self.assertEqual(items[0]["price"], 264000)
        self.assertEqual(items[0]["source_selection"], "direct-single")

    def test_usdt_derived_fallback_is_the_only_derived_quote_retained(self):
        items = [
            {"id": "usdt", "price": 263000, "derived": True},
            {"id": "btc", "price": 90000, "unit": "USDT", "price_irt": 900000000},
        ]
        module.drop_derived(items)
        self.assertEqual([x["id"] for x in items], ["usdt", "btc"])
        self.assertNotIn("price_irt", items[1])

    def test_iran_market_quotes_use_declared_toman_unit_and_source_timestamp(self):
        now = module.now_iso()
        payload = {"meta": {"unit": "toman", "stale": False}, "data": [
            {"symbol": "EUR_IRR_FREE", "currency": "IRT", "price": 291720,
             "timestamp": now, "change_pct": 0.37, "stale": False},
            {"symbol": "GBP_IRR_FREE", "currency": "IRR", "price": 3484400,
             "timestamp": now, "stale": False},
        ]}
        with patch.object(module, "get_json", return_value=payload):
            result = module.fetch_iran_market()
        self.assertEqual(result["eur"]["price"], 291720)
        self.assertEqual(result["eur"]["unit"], "IRT")
        self.assertEqual(result["eur"]["change_pct"], 0.37)
        self.assertEqual(result["gbp"]["price"], 348440)
        self.assertEqual(result["gbp"]["unit"], "IRT")

    def test_stale_secondary_currency_feed_is_rejected(self):
        payload = {"meta": {"unit": "toman", "stale": True}, "data": [
            {"symbol": "EUR_IRR_FREE", "currency": "IRT", "price": 291720,
             "timestamp": module.now_iso(), "stale": False},
        ]}
        with patch.object(module, "get_json", return_value=payload):
            self.assertEqual(module.fetch_iran_market(), {})

    def test_derived_currency_history_is_archived_but_not_published(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            archive_path = Path(folder) / "history-archive.json"
            lean_path = Path(folder) / "history.json"
            old_point = [module.parse_timestamp("2026-11-10T10:00:00Z"), 290000.0]
            archive_path.write_text(json.dumps({
                "v": 2, "seeded": ["eur", "btc"], "seed_attempted": {},
                "series": {"eur": [old_point], "btc": [old_point]},
            }), encoding="utf-8")
            checked = module.parse_timestamp("2026-11-11T12:20:00Z")
            with patch.object(module, "HIST_ARCHIVE", archive_path),                  patch.object(module, "HIST", lean_path),                  patch.object(module.time, "time", return_value=checked),                  patch.object(module, "seed_history"):
                result = module.update_history([
                    {"id": "eur", "price": 291000, "unit": "IRT", "method": "direct", "stale": False},
                    {"id": "btc", "price": 90000, "unit": "USD", "stale": False},
                ])
            self.assertEqual(result["unverified_currency_history"]["eur"], [old_point])
            self.assertNotIn("eur", result["seeded"])
            self.assertEqual(len(result["series"]["eur"]), 1)
            self.assertEqual(result["series"]["eur"][0][1], 291000)
            lean = json.loads(lean_path.read_text(encoding="utf-8"))
            self.assertEqual(lean["series"]["eur"][0][1], 291000)

    def test_fred_daily_energy_csv_is_parsed_without_api_key(self):
        previous_day = (module.datetime.datetime.now(module.datetime.timezone.utc).date() - module.datetime.timedelta(days=1)).isoformat()
        latest_day = module.datetime.datetime.now(module.datetime.timezone.utc).date().isoformat()
        def fake_urlopen(request, timeout=20):
            url = request.full_url
            if "DCOILBRENTEU" in url:
                series, values = "DCOILBRENTEU", f"{previous_day},90.0\n{latest_day},92.0\n"
            elif "DCOILWTICO" in url:
                series, values = "DCOILWTICO", f"{previous_day},85.0\n{latest_day},87.0\n"
            else:
                series, values = "DHHNGSP", f"{previous_day},3.0\n{latest_day},3.2\n"
            return FakeResponse(f"observation_date,{series}\n{values}")
        with patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = module.fetch_fred_energy()
        self.assertEqual(set(result), {"brent-spot", "wti-spot", "natural-gas"})
        self.assertEqual(result["brent-spot"]["price"], 92.0)
        self.assertEqual(result["brent-spot"]["backup_source"], "fred")
        self.assertEqual(result["brent-spot"]["market_type"], "daily-spot")
        self.assertAlmostEqual(result["brent-spot"]["change_pct"], 2.2222, places=3)
        self.assertEqual(result["natural-gas"]["price"], 3.2)


if __name__ == "__main__":
    unittest.main()
