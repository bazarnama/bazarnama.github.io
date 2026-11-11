# بازارنما API v1

API عمومی و بدون کلید برای استفاده در وب‌سایت و اپلیکیشن.

## آخرین قیمت‌ها

`GET https://bazarnama.github.io/api/v1/latest.json`

پاسخ شامل `generated_utc`، `fetched_utc` و آرایه `items` است. هر قلم دارای `id`، `price`، `unit`، `change_pct`، `stale`، `source_name` و `source_updated_utc` (در صورت وجود) است.

## تاریخچه هر دارایی

`GET https://bazarnama.github.io/api/v1/history/{asset_id}.json`

پاسخ شامل `id`، `unit`، `updated_utc` و `points` است. هر نقطه به شکل `{"timestamp": 1794000000, "price": 12345}` و زمان آن Unix UTC است.

## فهرست

`GET https://bazarnama.github.io/api/v1/index.json`

این API استاتیک است و با GitHub Actions تقریباً هر ۱۰ دقیقه بازسازی می‌شود. تاریخچه در مخزن نگه‌داری می‌شود؛ اجرای زمان‌بندی‌شده ممکن است گاهی با تأخیر انجام شود. داده‌های قدیمی با `stale: true` مشخص می‌شوند و نباید قیمت زنده تلقی شوند.
