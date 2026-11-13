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

## فیلدهای تازگی و اعتبار (در `latest.json`)

- `freshness.status`: یکی از `fresh`، `aging`، `stale`، `unknown`.
- `freshness.observed_utc`: زمان اعلام قیمت توسط منبع؛ `freshness.checked_utc`: زمان بررسی بازارنما؛ `generated_utc`: زمان ساخت فایل.
- `validation_*`، `secondary_*` و `source_discrepancy_pct`: نتیجه‌ی مقایسه با منبع مستقل دوم (فقط ارزهای اصلی). `validation_warning` یعنی اختلاف بیش از آستانه.
- `GET /api/v1/source-health.json`: وضعیت منابع و تعداد قلم‌ها به تفکیک وضعیت تازگی.

## سیاست پایداری

- مسیرها و نام فیلدهای فعلی در `v1` حذف یا تغییر نمی‌کنند؛ فقط فیلد اضافه می‌شود.
- تغییر ناسازگار فقط در مسیر جدید (`/api/v2/`) منتشر می‌شود.
- محدودیت درخواست ندارد، اما نباید بیش از یک بار در دقیقه فایل را بخوانید؛ داده هر چند دقیقه یک‌بار عوض می‌شود. فایل‌ها پشت CDN کش می‌شوند.
- تضمین SLA وجود ندارد.

مستندات کامل با نمونهٔ واقعی: https://bazarnama.github.io/api-docs.html
