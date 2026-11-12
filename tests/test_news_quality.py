import importlib.util, pathlib, unittest
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("news_quality", ROOT / "news_quality.py")
nq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nq)

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def raw(title, source="مهر", date="Thu, 12 Nov 2026 11:30:00 +0000", url=None):
    return {"title": title, "url": url or "https://example.ir/" + str(abs(hash(title + source))), "source": source, "date": date}


class ClassifyTests(unittest.TestCase):
    def test_whole_word_match_not_substring(self):
        self.assertIsNone(nq.classify("بازاریان زابل در سوگ بانوی مهربانی‌ها؛ بازار رنگ فاطمی گرفت")[0])

    def test_categories(self):
        self.assertEqual(nq.classify("قیمت دلار امروز پنجشنبه")[0], "currency")
        self.assertEqual(nq.classify("قیمت سکه امامی و طلای ۱۸ عیار کاهش یافت")[0], "gold")
        self.assertEqual(nq.classify("شاخص کل بورس صعودی شد")[0], "stock")
        self.assertEqual(nq.classify("قیمت خودرو در بازار امروز")[0], "auto")
        self.assertEqual(nq.classify("نهضت ملی مسکن در مهاباد")[0], "housing")
        self.assertEqual(nq.classify("افزایش قیمت برنج و روغن در بازار")[0], "commodities")
        self.assertEqual(nq.classify("تورم ماهانه کاهش یافت")[0], "macro")

    def test_single_weak_word_is_not_enough(self):
        self.assertIsNone(nq.classify("افتتاح بازار جدید میوه")[0])

    def test_two_weak_words_are_enough(self):
        self.assertEqual(nq.classify("قیمت‌ها در بازار تغییر کرد")[0], "macro")

    def test_off_topic_without_strong_term_is_dropped(self):
        self.assertIsNone(nq.classify("فوتبال: تیم ملی در بازار نقل و انتقالات")[0])

    def test_persian_digits_and_arabic_letters_are_normalized(self):
        self.assertEqual(nq.normalize("دلار ۱۲۳ ي ك"), "دلار 123 ی ک")

    def test_dollar_adjective_is_not_dollar(self):
        self.assertIsNone(nq.classify("بازی‌های موبایلی ۱۲۱ میلیارد دلاری")[0])


class DateTests(unittest.TestCase):
    def test_valid_rfc822(self):
        iso, st = nq.parse_date("Thu, 12 Nov 2026 11:30:00 +0000", NOW)
        self.assertEqual((iso, st), ("2026-11-12T11:30:00+00:00", "ok"))

    def test_missing_and_invalid(self):
        self.assertEqual(nq.parse_date("", NOW)[1], "missing")
        self.assertEqual(nq.parse_date("not a date", NOW)[1], "invalid")

    def test_naive_time_is_not_trusted(self):
        self.assertEqual(nq.parse_date("2026-11-12T10:00:00", NOW)[1], "invalid")

    def test_future_and_old(self):
        self.assertEqual(nq.parse_date((NOW + timedelta(hours=3)).isoformat(), NOW)[1], "future")
        self.assertEqual(nq.parse_date((NOW - timedelta(days=30)).isoformat(), NOW)[1], "too_old")

    def test_parsed_struct_tuple(self):
        self.assertEqual(nq.parse_date((2026, 11, 12, 10, 0, 0), NOW)[1], "ok")


class BuildTests(unittest.TestCase):
    def test_duplicates_across_sources_are_merged_and_credited(self):
        a = raw("قیمت دلار امروز پنجشنبه ۲۱ آبان ۱۴۰۵ افزایش یافت", "ایسنا")
        b = raw("قیمت دلار امروز پنجشنبه ۲۱ آبان ۱۴۰۵ افزایش یافت!", "مهر", date="Thu, 12 Nov 2026 11:00:00 +0000")
        items, stats = nq.build_items([a, b], NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["also_reported_by"], ["مهر"])
        self.assertEqual(stats["duplicates"], 1)

    def test_different_stories_are_not_merged(self):
        items, _ = nq.build_items([raw("قیمت دلار امروز افزایش یافت"), raw("قیمت سکه امروز کاهش یافت")], NOW)
        self.assertEqual(len(items), 2)

    def test_item_without_valid_date_is_excluded_and_counted(self):
        items, stats = nq.build_items([raw("قیمت دلار امروز", date=None)], NOW)
        self.assertEqual(items, [])
        self.assertEqual(stats["no_valid_date"], 1)

    def test_http_links_and_empty_titles_are_ignored(self):
        items, _ = nq.build_items([raw("قیمت دلار", url="http://x.ir/a"), raw("")], NOW)
        self.assertEqual(items, [])

    def test_output_keeps_legacy_fields_and_sorts_newest_first(self):
        older = raw("قیمت طلا امروز کاهش یافت", date="Thu, 12 Nov 2026 08:00:00 +0000")
        newer = raw("شاخص کل بورس امروز صعودی شد", date="Thu, 12 Nov 2026 11:00:00 +0000")
        items, _ = nq.build_items([older, newer], NOW)
        self.assertEqual([i["category"] for i in items], ["stock", "gold"])
        for key in ("title", "url", "source", "published_at"):
            self.assertIn(key, items[0])


if __name__ == "__main__":
    unittest.main()
