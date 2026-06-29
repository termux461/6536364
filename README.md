# VPN Telegram Bot + Admin Panel + Support Mini App

Бот на aiogram 3.x для продажи VPN-доступов через панель Remnawave, с веб-админкой
(FastAPI + Jinja2) и встроенной поддержкой через Telegram Mini App.

## Состав

- `bot/` — Telegram-бот (aiogram 3, FSM, антифлуд, принудительная подписка, i18n RU/EN)
- `webapp/` — Mini App поддержки: FastAPI backend (`webapp/api`) + статичный фронтенд (`webapp/static`)
- `panel/` — веб-панель администратора (FastAPI + Jinja2): хосты, тарифы, платёжки, тикеты, рассылки, конструктор меню
- `database/` — модели SQLAlchemy (async) и сессии
- `nginx/` — конфиг reverse-proxy

## Быстрый старт (Docker)

1. Скопируйте `.env.example` в `.env` и заполните токен бота, ID админов, ключи платёжек.
2. `docker compose up -d --build`
3. Бот поднимется и сам создаст таблицы в Postgres при старте.
4. Откройте `http://<host>/panel/login` (логин/пароль из `PANEL_ADMIN_LOGIN`/`PANEL_ADMIN_PASSWORD`).
5. Добавьте хост Remnawave и хотя бы один тариф в панели — после этого кнопка
   «Купить VPN» в боте станет рабочей.
6. В панели → «Платёжки» включите нужные способы оплаты (Stars/CryptoBot/ЮKassa
   включены по умолчанию, но реально работают только те, для которых заданы ключи в `.env`).
7. `WEBAPP_URL` в `.env` должен указывать на публичный HTTPS-адрес `/webapp`
   (Telegram WebApp требует HTTPS) — настройте домен + Certbot перед продакшен-запуском.

## SSL (Certbot)

Nginx слушает 80/443, но сертификаты не генерируются автоматически. Разово получите их:

```
docker run --rm -v ./nginx/certbot/www:/var/www/certbot -v ./nginx/certbot/conf:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot -d your-domain.example
```

Затем добавьте `server { listen 443 ssl; ... }` блок в `nginx/conf.d/app.conf` со ссылками на
полученные сертификаты и настройте автопродление по cron.

## Локальный запуск без Docker

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)   # либо используйте python-dotenv
python -m bot.main                     # бот
uvicorn webapp.api.main:app --port 8001  # Mini App backend
uvicorn panel.main:app --port 8002       # админ-панель
```

## Платёжные методы

Каждый адаптер реализует единый интерфейс `create_payment / check_payment / webhook_handler`
(`bot/services/payments/`). Доступность метода для пользователей переключается в
панели администратора («Платёжки») или через бот-команду `/admin` → «💳 Платёжки» —
запись хранится в таблице `payment_methods` и не требует деплоя.

- **Telegram Stars** — работает «из коробки» через `Bot.create_invoice_link`, без внешних ключей.
- **CryptoBot** — нужен `CRYPTOBOT_API_TOKEN` от `@CryptoBot`.
- **ЮKassa** — нужны `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`.

## Remnawave

`bot/services/remnawave.py` — тонкий REST-клиент (create/extend/delete user,
получение subscription URL). Хосты добавляются через панель администратора
(`/panel/hosts`) или через бот-команду `/admin` → «🖥 Хосты».

## Известные ограничения / TODO

- SSH-спидтест ноды не реализован (есть поля `ssh_*` в модели `Host` под будущую интеграцию
  через `asyncssh`/`paramiko`); сейчас статус серверов считается через HTTP(S)-пинг.
- Webhook-эндпоинты для CryptoBot/ЮKassa реализованы в `webapp/api/main.py`:
  `POST /api/webhooks/cryptobot` (с проверкой подписи `Crypto-Pay-API-Signature`)
  и `POST /api/webhooks/yookassa`. Зарегистрируйте `https://<домен>/api/webhooks/cryptobot`
  в `@CryptoBot` → Crypto Pay → My Apps → Webhooks, и `https://<домен>/api/webhooks/yookassa`
  в личном кабинете ЮKassa. У ЮKassa нет подписи вебхука — безопасность обеспечивается
  IP-allowlist'ом ЮKassa на уровне Nginx/firewall (см. их документацию за актуальным списком IP).
  Кнопка «Я оплатил» в боте продолжает работать как запасной вариант (polling) независимо
  от вебхуков.
- TON Connect не реализован (см. ТЗ, опциональный пункт).
