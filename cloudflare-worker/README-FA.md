# رله‌ی قیمت زنده (Cloudflare Worker)

این Worker قیمت‌های نرخ‌آرا را می‌گیرد، تازگی هر قیمت را حساب می‌کند و ۶۰ ثانیه در کش لبهٔ Cloudflare نگه می‌دارد. سایت (اگر آدرسش تنظیم شود) اول از آن می‌خواند و اگر در دسترس نبود، مثل قبل از `data/prices.json` و بعد از `api/v1/latest.json`.

- قیمتی نمی‌سازد و تبدیل نمی‌کند؛ اقلام مشتق‌شده از دلار را حذف می‌کند.
- نمی‌تواند تازه‌تر از آنچه نرخ‌آرا منتشر کرده باشد بسازد؛ فقط تأخیر GitHub Actions را دور می‌زند.
- پلن رایگان Cloudflare: ۱۰۰٬۰۰۰ درخواست در روز. با بازدید زیاد، پلن پولی یا افزایش فاصلهٔ بازخوانی لازم می‌شود.

## راه‌اندازی از داشبورد (بدون نصب چیزی)
1. در https://dash.cloudflare.com بروید به **Workers & Pages** ← **Create** ← **Create Worker**؛ نام: `bazarnama-live` ← **Deploy**.
2. **Edit code** را بزنید، همهٔ کد پیش‌فرض را پاک کنید و محتوای `worker.js` همین پوشه را بچسبانید ← **Deploy**.
3. آدرس Worker شبیه `https://bazarnama-live.<نام‌شما>.workers.dev` است. در مرورگر `…/live.json` را باز کنید؛ باید JSON قیمت‌ها را ببینید.
4. (برای دامنهٔ اختصاصی) در **Settings ← Variables** متغیر `ALLOWED_ORIGINS` را برابر `https://bazarnama.github.io,https://دامنه-شما` بگذارید.
5. در مخزن فایل `live-config.js` را باز کنید و بنویسید:
   `window.BAZARNAMA_LIVE_URL = "https://bazarnama-live.<نام‌شما>.workers.dev/live.json";`
6. فایل را commit کنید. از همان لحظه صفحهٔ اصلی از Worker می‌خواند. برای برگشت، مقدار را دوباره خالی کنید.

## راه‌اندازی با خط فرمان (اختیاری)
```
cd cloudflare-worker
npx wrangler deploy
```

## تست محلی
`node worker.test.mjs`
