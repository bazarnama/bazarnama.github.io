import importlib.util, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tp", ROOT / "tools" / "telegram_post.py")
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)


def doc(**over):
    items = [{"id": i, "price": p, "unit": "IRT", "change_pct": 1.5} for i, p in
             (("usd", 268650.0), ("eur", 297178.0), ("gold-18k", 25400881.0), ("btc", 90000.5))]
    for it in items:
        it.update(over.get(it["id"], {}))
    return {"items": items}


class TelegramMessageTests(unittest.TestCase):
    def test_message_has_latin_digits_and_site_link(self):
        text = tp.build_message(doc())
        self.assertIn("دلار: 268,650 تومان 🟢 +1.50%", text)
        self.assertIn("https://bazarnama.github.io", text)
        self.assertFalse(any(c in text for c in "۰۱۲۳۴۵۶۷۸۹"))

    def test_stale_prices_are_left_out(self):
        text = tp.build_message(doc(usd={"stale": True}))
        self.assertNotIn("دلار:", text)

    def test_too_few_fresh_prices_means_no_post(self):
        self.assertIsNone(tp.build_message(doc(usd={"stale": True}, eur={"stale": True})))
        self.assertIsNone(tp.build_message({}))


if __name__ == "__main__":
    unittest.main()
