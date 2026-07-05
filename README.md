# AmneziaVPN Bot

Telegram-бот для продажи конфигураций AmneziaWG с балансовой системой.

## Структура

```
bot.py                    # Точка входа
config.py                 # Переменные окружения
handlers/
  start.py                # /start, главное меню
  buy.py                  # Покупка тарифа с баланса, мои подписки
  balance.py              # Пополнение: Platega + Telegram Stars
  promo.py                # Промокоды + партнёрская программа
  admin.py                # /admin — тарифы, промокоды, статистика
  webhook.py              # Platega webhook (aiohttp :8080)
services/
  database.py             # aiosqlite — все таблицы
  wgeasy.py               # REST API клиент wg-easy
  platega.py              # Генерация ссылки + верификация вебхука
  activation.py           # Создание пира + отправка .conf файла
  scheduler.py            # Удаление истёкших пиров
keyboards/
  inline.py               # Все InlineKeyboard
```

## Поток оплаты

```
Пользователь пополняет баланс
  → Platega/Stars → вебхук → баланс+
  → /buy → выбор тарифа
  → атомарное списание с баланса (защита от двойной оплаты)
  → создание WG пира (wg-easy API)
  → отправка amnezia.conf файла
  ↳ при сбое создания пира деньги возвращаются на баланс
```

### Продление

Если на выбранном протоколе уже есть активная подписка, повторная покупка
её **продлевает**: дни добавляются к текущему сроку, пир не пересоздаётся,
старый `.conf` продолжает работать.

### Перевыдача конфига

В разделе **«Мои подписки»** для каждой активной подписки есть кнопка
скачать `.conf` заново (конфиг тянется из wg-easy по сохранённому `wg_peer_id`).

## Деплой

### 1. wg-easy на VPS

```bash
docker run -d \
  --name=wg-easy \
  -e WG_HOST=YOUR_VPS_IP \
  -e PASSWORD=YOUR_WG_PASSWORD \
  -v ~/.wg-easy:/etc/wireguard \
  -p 51820:51820/udp \
  -p 51821:51821/tcp \
  --cap-add=NET_ADMIN --cap-add=SYS_MODULE \
  --sysctl="net.ipv4.conf.all.src_valid_mark=1" \
  --sysctl="net.ipv4.ip_forward=1" \
  --restart unless-stopped \
  ghcr.io/wg-easy/wg-easy
```

### 2. Бот

```bash
cp .env.example .env && nano .env
pip install -r requirements.txt
python bot.py
```

### 3. nginx → webhook

```nginx
location /platega/webhook {
    proxy_pass http://127.0.0.1:8080;
}
```

В кабинете Platega укажи URL вебхука:
```
https://yourdomain.com/platega/webhook
```

### systemd

```ini
[Unit]
Description=AmneziaVPN Bot
After=network.target

[Service]
WorkingDirectory=/root/amnezia-bot
EnvironmentFile=/root/amnezia-bot/.env
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Тарифы по умолчанию

| Тариф     | Дней | Цена |
|-----------|------|------|
| 1 месяц   | 30   | 129₽ |
| 3 месяца  | 90   | 349₽ |
| 6 месяцев | 180  | 599₽ |
| 1 год     | 365  | 999₽ |

Редактируются через `/admin` без перезапуска.

## Telegram Stars — курс

По умолчанию: 1 Star = 2₽. Меняется в `keyboards/inline.py` → `stars_amount_kb()`.
