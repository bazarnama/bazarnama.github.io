# برنامه بازگشت

همه تغییرات این نسخه در یک commit یا PR جدا ثبت شود تا با `git revert <commit>` برگردد.
- تغییر freshness/jump فقط `update_prices.py` است؛ بازگشت = برگرداندن همان فایل.
- کلید `pending` در `data/history-archive.json` اختیاری است؛ نسخه قدیمی آن را نادیده می‌گیرد.
- فایل‌های README به `docs/` منتقل شده‌اند (بدون حذف).
- ظاهر: تنها تغییر در `index.html` escape کردن نام دارایی در `<option>` است و خروجی برای نام‌های عادی یکسان است.
- پیش از انتشار: `python3 -m unittest discover -s tests` و ورود دستی workflow قیمت با `workflow_dispatch`.
