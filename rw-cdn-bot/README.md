# Remnawave + Yandex Cloud CDN — бот автонастройки

Telegram-бот, который продаёт услугу автоматической настройки связки
**Remnawave + Yandex Cloud CDN + XHTTP** и после подтверждённой оплаты выполняет её сам:
подключается к Origin Server по SSH, готовит сервер, поднимает Remnanode, создаёт объекты
в Remnawave, выпускает сертификат и CDN-ресурс в Yandex Cloud, настраивает DNS и проверяет
результат.

---

## 1. Что делает проект

После оплаты бот проходит весь путь без ручных команд:

```
Получить данные → Проверить Origin Server → Подготовить Origin Server → Docker → Nginx → SSL
→ Remnawave Profile → Remnawave Node → Установить Remnanode → Remnawave Host
→ Yandex Certificate → Yandex CDN → CNAME от Yandex → DNS → Проверка DNS/CDN/XHTTP
→ Health Check → Завершить заказ
```

Прогресс показывается в **одном** сообщении, которое редактируется, а не в потоке уведомлений.

> Разработчику, который впервые видит проект: начните с **[ARCHITECTURE.md](ARCHITECTURE.md)** —
> там разобрана логика кода, а не инструкция по запуску.

## 2. Архитектура

Итоговая схема трафика — **без каскада**, без зарубежного выхода, без geoip/geosite-маршрутизации:

```
                    INTERNET
                        │
                        ▼
               cdn.example.com
                        │  CNAME
                        ▼
             Yandex Cloud CDN
                        │  HTTPS
                        ▼
             origin.example.com
                        │
                        ▼
                Origin Server
                        │
                        ▼
                  Nginx :443
                        │
                        ▼
              127.0.0.1:9001
                        │
                        ▼
             Remnawave Node
                        │
                        ▼
                  Xray / XHTTP
```

**Терминология.** Машина клиента — всегда **Origin Server** (`origin_servers`, `origin_ip`,
`origin_domain`, `origin_port`, `origin_status`). Объект внутри панели — **Remnawave Node**.
Remnawave Node устанавливается на Origin Server; это разные сущности.

Сервисы:

| Компонент | Роль |
|---|---|
| `bot` | aiogram-поллинг + HTTP-сервер вебхуков |
| `worker` | выполняет deployment из очереди Redis |
| `broadcast` | рассылки с ограничением скорости |
| `postgres` | данные |
| `redis` | FSM-хранилище и очередь задач |

Слои кода: `bot/` (интерфейс) → `services/` (Remnawave, Yandex, платежи, SSH, DNS, deployment)
→ `repositories/` (доступ к данным) → `models/`.

## 3. Требования

* Docker и Docker Compose
* Домен и доступ к его DNS
* Публичный HTTPS-адрес для вебхуков (nginx перед ботом)
* Аккаунты Platega и/или ЮKassa

Для каждого заказа клиент предоставляет: URL и API-токен Remnawave, IP/SSH Origin Server,
Origin Domain, CDN Domain, email для Let's Encrypt, Folder ID и ключ сервисного аккаунта Yandex Cloud.

## 4. Установка

```bash
git clone <repo> rw-cdn-bot && cd rw-cdn-bot
cp .env.example .env
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # → SECRET_ENCRYPTION_KEY
$EDITOR .env
```

Локально без Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.main            # бот + вебхуки
python -m app.workers.deployment_worker
python -m app.workers.broadcast_worker
```

## 5. Docker

```bash
docker compose up -d --build
docker compose logs -f bot worker
```

Миграции применяет отдельный сервис `migrate` перед стартом `bot` и `worker`.
У каждого сервиса задан healthcheck, restart policy, volumes и ротация логов.

## 6. Environment variables

Все переменные — в `.env.example`. Ключевые:

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN`, `ADMIN_IDS` | Telegram |
| `DATABASE_URL`, `REDIS_URL` | инфраструктура |
| `WEBHOOK_BASE_URL`, `WEBHOOK_PORT` | адрес приёма колбэков |
| `PLATEGA_MERCHANT_ID`, `PLATEGA_API_KEY`, `PLATEGA_WEBHOOK_SECRET` | Platega |
| `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_ALLOWED_IPS` | ЮKassa |
| `SECRET_ENCRYPTION_KEY` | ключ шифрования секретов в БД |
| `DEPLOY_MAX_ATTEMPTS`, `DEPLOY_RETRY_DELAYS` | политика повторов |

Ничего не хардкодится: IP, домены, токены, цены, Telegram ID, CNAME Yandex и UUID Remnawave
берутся из настроек, БД или API. Единственные фиксированные значения — технические параметры
схемы: `127.0.0.1:9001`, путь `/video/download`, порт Remnawave Node `2222`.

## 7. Telegram Bot

Меню пользователя: 🚀 Автонастройка · 💰 Купить настройку · 📋 Мои заказы · 📖 Инструкция · 🆘 Поддержка.

Сбор данных — пошаговый FSM. Каждый секрет (SSH-ключ, пароль, API-токен, ключ сервисного
аккаунта, токен Cloudflare) шифруется и сообщение с ним удаляется из чата. Обратно секреты
не отдаются никогда.

## 8. Platega

`POST {PLATEGA_API_URL}/transaction/process` с заголовками `X-MerchantId` / `X-Secret`.
Колбэк приходит на `POST /webhooks/platega` с теми же заголовками и телом
`{id, amount, currency, status, paymentMethod}`. Статус `CONFIRMED` считается оплатой —
но только после повторной проверки через `GET /transaction/{id}`.

Platega работает в рублях, БД хранит копейки; конвертация выполняется в одном месте
(`app/services/payments/base.py`) через `Decimal`, без float.

## 9. YooKassa

`POST https://api.yookassa.ru/v3/payments` (Basic auth + `Idempotence-Key`).
Уведомления приходят на `POST /webhooks/yookassa`. Подписи у ЮKassa нет, поэтому
подлинность проверяется по списку IP (`YOOKASSA_ALLOWED_IPS`) **и** повторным запросом
`GET /v3/payments/{id}`.

## 10. Remnawave

Клиент `app/services/remnawave/client.py` использует только документированные эндпоинты
(собраны в `endpoints.py`): `/config-profiles`, `/nodes`, `/hosts`, `/internal-squads`,
`/system/*`. Если операции нет в документированном API — поднимается
`RemnawaveUnsupportedOperation`, эндпоинты не выдумываются.

Создаётся профиль `cdn` с одним inbound (`app/services/remnawave/templates.py` — единственное
место, где эти параметры заданы):

```
tag: XHTTP_LTE_YANDEX · listen 127.0.0.1 · port 2090 · vless · decryption none
network xhttp · security none · mode packet-up · path /api/v1/sync
xPaddingKey _dc · xPaddingHeader X-Cache · xPaddingMethod tokenish
xPaddingPlacement queryInHeader · xPaddingObfsMode true · uplinkHTTPMethod GET
scMaxEachPostBytes 524288 · scMaxConcurrentPosts 1 · scMinPostsIntervalMs 150
```

Routing: весь трафик этого inbound уходит в `DIRECT`. Никакого каскада, зарубежного выхода
и geo-правил.

Host указывает на **CDN Domain** (не на внутренний CNAME Yandex): port 443, SNI и Host —
CDN Domain, path `/api/v1/sync`, TLS, ALPN `h2,http/1.1`, отпечаток `chrome`, и тот же блок
`extra` — тест отдельно сверяет, что обе стороны совпадают байт в байт, потому что
рассинхрон здесь даёт молчаливый обрыв, а не понятную ошибку.

Если скорость низкая — в `XHTTP_THROUGHPUT_TUNING` лежат значения из гайда
(`scMaxConcurrentPosts: 2`, `scMinPostsIntervalMs: 80`).

Все создающие операции идемпотентны: профиль ищется по имени, нода — по адресу, host — по адресу.

### SECRET_KEY ноды

Значение, которое Remnanode ждёт в `SECRET_KEY`, ищется по цепочке — ничего не генерируется локально:

1. значение, введённое администратором вручную (кнопка **🔑 SECRET_KEY** в карточке заказа);
2. поля самого объекта ноды (`nodeSecret`, `secretKey`, `sslCert`) — их отдают не все сборки;
3. `GET /keygen/pub-key`, а на старых сборках `GET /keygen` — это общий для панели сертификат,
   тот же, что панель показывает в карточке ноды.

Если ни один источник не сработал, deployment останавливается с понятным текстом и просьбой
вставить ключ вручную — вместо генерации нерабочего docker-compose.

## 10.1 Node installer

Установкой ноды занимается `app/services/deployment/node_installer.py`, а не shell-скрипт.

**Что он делает**

* Проверяет наличие `docker compose` (иначе — постоянная ошибка, ретраить бессмысленно).
* Пишет `/opt/remnanode/.env` c правами `600` и `docker-compose.yml` через SFTP.
  Секрет никогда не попадает в командную строку, в лог и в сам compose-файл —
  compose ссылается на `.env`, поэтому `docker compose config` его не печатает.
* Поднимает контейнер (`pull` + `up -d`), ставит logrotate на `/var/log/remnanode`
  и ротацию json-file логов самого контейнера.
* Проверяет результат: статус контейнера, `RestartCount`, ID образа, слушается ли порт 2222,
  последние 60 строк лога.

**Два формата переменных.** В обращении две задокументированные схемы:
`NODE_PORT` + `SECRET_KEY` (текущая) и `APP_PORT` + `SSL_CERT` (старая). Установщик пишет
текущую; если контейнер не стартовал и в логе видно, что образ ждёт старые имена, `.env`
переписывается в legacy-формате и делается ровно одна повторная попытка.

**Идемпотентность.** Повторный запуск с тем же секретом и работающим контейнером не делает
ничего: `.env` сравнивается с желаемым, `docker compose up` не вызывается. Принудительная
переустановка — `install(force=True)`.

**Классификация ошибок.** Повреждённый ключ или ключ от другой панели и занятый порт 2222 —
`PermanentError` (ретраи не помогут). Всё остальное — `TransientError`, попадает в обычную
схему повторов `5s → 15s → 30s`.

**Из админки** (карточка заказа, `/order <id>`):

| Кнопка | Действие |
|---|---|
| 🔑 SECRET_KEY | принять ключ сообщением, зашифровать, удалить сообщение из чата |
| 🩺 Нода | подключиться по SSH и показать статус, образ, перезапуски, порт и хвост лога |
| ♻️ Переустановить ноду | сбросить шаг `install_remnanode` и поставить деплой в очередь |

Переустановка идёт через очередь, а не inline: SSH-сессией владеет worker, у него же
блокировка по заказу — так два одновременных деплоя одного заказа невозможны.

## 11. Yandex Cloud

* IAM: `POST https://iam.api.cloud.yandex.net/iam/v1/tokens` (JWT PS256 из ключа сервисного аккаунта)
* Certificate Manager: `certificates/requestNew` с `challengeType: DNS_CNAME`, затем
  `GET /certificates/{id}?view=FULL` — оттуда берётся `challenges[].dnsChallenge`
* CDN: `originGroups`, `resources`, `GET /cdn/v1/cname` для CNAME провайдера,
  `provider/activate`
* Cloud DNS: `zones`, `zones/{id}:updateRecordSets`

Настройки CDN-ресурса для VPN-трафика: кеширование выключено (CDN и браузер), кеширование
query-параметров выключено, gzip выключен, сегментация больших файлов выключена,
Host-заголовок принудительно равен Origin Domain, разрешены `GET, HEAD, OPTIONS`.
`ignoreCookie` относится только к ключу кеша — сам заголовок `Cookie` доходит до nginx/Xray,
без него xHTTP не работает (`chunk`, `visitor_id`).

### Права в Yandex Cloud

Нужны независимо от способа авторизации — cookie и OAuth действуют от имени пользователя,
ключ от имени сервисного аккаунта, но роли на **каталог** (Folder) должны быть в обоих случаях:

| Роль | Зачем |
|---|---|
| `certificate-manager.editor` | выпуск сертификата Let's Encrypt для CDN Domain |
| `cdn.editor` | создание origin-группы и CDN-ресурса, включение провайдера |
| `dns.editor` | только если DNS-зона ведётся в Yandex Cloud DNS |

**Проверка выполняется дважды и заранее:**

* при вводе данных заказа — бот делает по одному дешёвому чтению в каждый сервис
  (`check_access`) и, если прав нет, отвечает конкретно: какой возможности не хватает и
  какую роль выдать. Клиент узнаёт об этом до оплаты работы, а не в середине настройки;
* на шаге `validate_data` — тот же preflight перед тем, как что-либо трогать на сервере.
  `403` → постоянная ошибка с названием роли; `5xx` → временная, уходит в обычные повторы,
  а не выглядит как «не выдали права».

Роли проверяются эмпирически — реальным вызовом API, а не разбором списка прав, — поэтому
проверка останется верной, даже если Yandex переименует роль; имя роли фигурирует только в
подсказке.

**Один каталог для сертификата и CDN.** Yandex требует, чтобы сертификат лежал в том же
каталоге, что и CDN-ресурс, иначе операция падает с `folder ids of user and certificate
don't match`. Перед созданием ресурса бот сверяет `folderId` сертификата с каталогом заказа
и говорит об этом прямо, вместо того чтобы прокидывать наверх невнятную ошибку Yandex.

### Авторизация в Yandex Cloud

Три способа, выбираются при сборе данных заказа (`app/services/yandex/auth.py`):

| Способ | Как получает IAM-токен | Живёт | Статус |
|---|---|---|---|
| 🔑 Ключ сервисного аккаунта | JWT PS256 → `POST /iam/v1/tokens {"jwt"}` | бессрочно | документирован, по умолчанию |
| 🎫 OAuth-токен | `POST /iam/v1/tokens {"yandexPassportOauthToken"}` | год | документирован |
| 🍪 Cookie браузера | сессия → эндпоинт обмена → токен | часы-дни | **не документирован Yandex** |

**Про cookie отдельно.** Веб-интерфейсы Yandex Cloud аутентифицируют пользователя по
`yc_session`. Единая логическая сессия начинается в `auth.yandex.cloud`, но сама cookie
выдаётся отдельно для каждого сервисного домена (консоль, Cloud Center, DataLens и т. д.).
Из этого следуют два правила, которые проверяются до первого запроса:

* нужен именно `yc_session`. Экспорт с `Session_id` — это Яндекс ID, другая сессия;
  бот отвечает на такой файл отдельным понятным сообщением, а не общей ошибкой;
* cookie должны быть сняты с того же домена, на котором живёт эндпоинт обмена. Куки
  `console.yandex.cloud` не отправятся на `datalens.yandex.cloud` — несовпадение ловится
  сразу, а не превращается в необъяснимый редирект на страницу логина.

Yandex не публикует обмена cookie на IAM-токен, поэтому URL обмена и поле с токеном заданы
конфигурацией, а не в коде:

```
YANDEX_COOKIE_AUTH_ENABLED=true
YANDEX_COOKIE_EXCHANGE_URL=          # пусто — эндпоинт определяется автоматически
YANDEX_COOKIE_TOKEN_FIELD=iamToken   # поддерживается вложенность: data.token
```

Если `YANDEX_COOKIE_EXCHANGE_URL` пуст, эндпоинт **подбирается один раз** по доменам, для
которых выданы cookie (`discover_exchange_url`): пробуются несколько путей консоли, и попыткой
считается только ответ `200` с JSON, где лежит значение, похожее на токен. HTML, редирект на
логин и `404` — промахи. Не нашлось ничего — заказ не стартует с советом перейти на OAuth,
путь консоли не угадывается. Найденный эндпоинт кэшируется на процесс и сбрасывается, как
только начинает отвечать `401/403` — значит, догадка была неверной. Автоопределение можно
выключить (`discover=False`), тогда без заданного URL провайдер откажется стартовать.

Длина значения проверяется только при слепом подборе: если поле указано в
`YANDEX_COOKIE_TOKEN_FIELD` явно, оно берётся как есть.

**Форматы cookie.** Принимается строка или файл, формат определяется по содержимому
(`app/services/yandex/cookies.py`):

| Что прислали | Формат |
|---|---|
| строка из DevTools или `document.cookie` | `header` |
| `.cookie` / `cookies.txt` | `netscape` (строки `#HttpOnly_` тоже читаются) |
| `.json` из EditThisCookie / Cookie-Editor | `json_list` |
| `.json` storage state из Playwright / Puppeteer | `json_state` |
| плоский `{"Session_id": "..."}` | `json_map` |

Из файла берутся только домены Yandex — полный дамп браузера содержит сотни чужих cookie,
и отправлять их незачем. Просроченные записи отбрасываются.

**Cookie не сохраняются.** В базе для них нет колонки (миграция `0003` удаляет её, если БД
создавалась раньше). Разобранная **банка** (`CookieJar.dumps()` — имя, значение, домен и срок
жизни каждой cookie, а не плоская строка `name=value`) кладётся в Redis-хранилище
`app/services/vault.py` зашифрованной и удаляется:

* сразу после шага `configure_dns` — это последний шаг, которому может понадобиться Yandex
  (провайдером DNS бывает Cloud DNS, живущий в том же каталоге);
* при любом терминальном исходе деплоя (`completed`, `failed`, `stopped`);
* сама по себе по TTL, если воркер упал и ничего не вызвало удаление.

TTL берётся из самой сессии: час по умолчанию, но меньше, если cookie умрут раньше. Хранится
именно банка, а не заголовок, потому что воркеру нужны и домен (он решает, какому хосту банку
вообще можно показать), и срок (он решает, стоит ли пытаться).

Redis используется потому, что cookie обязаны пересечь одну границу процессов: бот их
принимает, воркер выполняет настройку. Больше нигде они не задерживаются.

Что сделано, чтобы истечение сессии не ломало заказы:

* **Проверка при вводе.** Любые данные (ключ, OAuth, cookie) сразу проверяются реальным
  запросом к Certificate Manager. Не работают — клиент узнаёт об этом сейчас, а не через
  три часа посреди деплоя.
* **Истечение — не провал.** Мёртвая сессия поднимает `ReauthRequired`, deployment уходит
  в статус `waiting_reauth`, а не `failed`. Ретраев нет — повторять запросы к умершей
  сессии бессмысленно.
* **Возобновление.** Клиенту приходит просьба прислать свежие данные командой
  `/reauth <id>`; после проверки настройка продолжается с того же шага. Команда
  зарегистрирована на отдельном роутере, включённом до FSM сбора данных, поэтому работает
  даже когда пользователь застрял в середине опроса.
* **Разделение причин.** Редирект на логин, HTML вместо JSON и 401/403 → «нужна новая
  сессия». Отсутствие настроенного поля с токеном → ошибка конфигурации, а не reauth.
* Cookie нормализуются при сохранении: в Redis лежит разобранная банка, зашифрованная,
  а не вставленный блоб. Заголовок собирается уже под конкретный хост — на эндпоинт обмена
  уходят только те cookie, которые туда отправил бы браузер.
* **Просроченная банка не идёт в сеть.** Пустая или мёртвая сессия сразу поднимает
  `ReauthRequired`, а не превращается в ошибку разбора файла.

Способ остаётся неподдерживаемым Yandex: сессия привязана к личному аккаунту, а не к
аккаунту клиента, и консольные эндпоинты могут поменяться без предупреждения. Для продакшена
по-прежнему рекомендуется ключ сервисного аккаунта с ролями выше.

## 12. DNS

Поддерживаются три режима: **Cloudflare API**, **Yandex Cloud DNS**, **вручную**.
Записи Cloudflare создаются всегда с выключенным проксированием (серое облако).

Нужные записи:

| Тип | Имя | Значение |
|---|---|---|
| A | `origin.example.com` | IP Origin Server |
| CNAME | `_acme-challenge.cdn.example.com` | значение из Certificate Manager |
| CNAME | `cdn.example.com` | CNAME, полученный от Yandex CDN |

В ручном режиме бот показывает запись и кнопку **🔄 Проверить DNS**; по нажатию выполняется
реальный resolve через публичные резолверы, и при успехе deployment продолжается сам.
Заказ не завершается, пока DNS не подтверждён.

## 13. Webhooks

```
POST /webhooks/platega
POST /webhooks/yookassa
GET  /healthz
```

Вебхук делает минимум: валидация → одна транзакция БД → пометка оплаты → постановка задачи
в очередь → `200`. Никаких SSH, Docker и облачных вызовов внутри обработчика.

Проверяется: подпись/учётные данные, событие, payment ID, сумма, валюта, заказ, статус,
дубликат. Повторный колбэк (2, 5, 20 раз) не создаёт второй deployment — уникальный ключ
`(provider, event_key)` в `payment_events` делает обработку идемпотентной.

## 14. Первый запуск

1. `docker compose up -d --build`
2. Отправить боту `/admin` → **💰 Цены** → задать цену тарифа `auto_setup` → включить его
   (пока цена 0, тариф включить нельзя).
3. Прописать URL вебхуков в кабинетах Platega и ЮKassa.
4. Проверить `curl https://<домен>/healthz`.

## 15. Deployment flow

Шаги (`app/services/deployment/steps.py`) выполняются по порядку, каждый пишется в
`deployment_steps` со статусом `started/success/failed/retry/waiting`:

```
validate_data · check_origin · prepare_origin · configure_firewall · configure_sysctl
configure_swap · install_docker · install_nginx · configure_site · configure_origin_dns
verify_origin_dns · configure_ssl · configure_nginx · create_remnawave_profile
create_remnawave_node · install_remnanode · create_remnawave_host · create_yandex_certificate
configure_acme_dns · verify_certificate · create_yandex_cdn · get_yandex_cname
configure_dns · verify_dns · health_check · complete
```

**Идемпотентность.** Перезапуск worker'а не создаёт ничего заново: успешные шаги
пропускаются, а перед созданием каждого ресурса выполняется поиск существующего
(profile / node / host / certificate / CDN / DNS).

**Повторы.** Временные ошибки (таймаут API или SSH, непрогруженный DNS, неготовый ресурс
Yandex, `Pending` у сертификата) повторяются по схеме `5s → 15s → 30s`
(`DEPLOY_RETRY_DELAYS`, `DEPLOY_MAX_ATTEMPTS`).

**Ожидание — не ошибка.** Если DNS ещё не разошёлся или сертификат в `Validating`,
deployment переходит в `waiting_dns` / `waiting_certificate`, паркуется в отложенной очереди
и возобновляется автоматически.

**Health check.** Проверяются nginx, docker, контейнер remnanode, порты 80/443/SSH/2222,
`https://origin/` → 200, `https://cdn/` → 200. Порт 9001 обязан слушать только на
`127.0.0.1` — если он открыт наружу, проверка не проходит. Код `400` на
`/video/download` для обычного `curl` — ожидаемый результат: путь дошёл до Xray, а `curl`
не является VLESS/xHTTP-клиентом.

## 16. Админ-панель

`/admin` внутри бота: 👥 Пользователи · 📦 Заказы · 💰 Цены · 📢 Рассылка · 🔧 Техработы ·
📊 Статистика · 📋 Логи.

* **Пользователи** — карточка (`/user <telegram_id>`), блокировка, сообщение пользователю,
  число заказов и сумма трат.
* **Заказы** — фильтры по статусу, карточка (`/order <id>`) со всеми ID ресурсов,
  кнопки ▶️ Continue / 🔄 Retry / 🛑 Stop.
* **Цены** — название, описание, цена, валюта, активность; изменение применяется сразу.
* **Техработы** — ON/OFF и редактируемый текст; при ON покупка недоступна (админам — доступна).
* **Рассылка** — создание, предпросмотр, запуск, остановка; счётчики отправлено / ошибки /
  заблокировали бота / FloodWait; отправка через очередь с ограничением скорости.
* **Статистика** — сегодня / 7 дней / 30 дней / за всё время.

## 16.1 Тестовый прогон без оплаты

Команда `/testorder` (только для админов) создаёт заказ с нулевой суммой, сразу переводит его
в сбор данных и дальше выполняет ровно тот же путь, что у настоящего клиента: SSH, Remnawave,
Yandex, DNS, health check.

Платёжный тракт при этом не трогается: не создаётся ни фиктивный `Payment`, ни поддельный
вебхук, проверки подписи и суммы никуда не деваются. Просто заказ создаётся уже оплаченным
на 0 ₽ и помечается в `audit_logs` как тестовый; в карточке заказа он подписан
«🧪 тестовый, без оплаты».

Остановить в любой момент: `/admin → 📦 Заказы → 🛑 Stop`.

Для теста всё равно нужны настоящие Origin Server, панель Remnawave, домены и доступ
к Yandex Cloud — бот настраивает реальную инфраструктуру, а не симулирует её.

## 17. Troubleshooting

| Симптом | Причина и что делать |
|---|---|
| `certbot` не выпускает сертификат | A-запись Origin Domain ещё не разошлась или проксируется (нужен DNS only) |
| CDN отдаёт не 200 | сертификат применяется на edge-нодах Yandex до 30 минут; deployment сам повторит |
| Клиент получает `400` на `/video/download` | клиент игнорирует `extra` — используйте sing-box-подписку вместо голого `vless://` |
| `remnanode` не поднимается | посмотреть `docker compose logs` в `/opt/remnanode`, проверить доступность панели с Origin Server по порту 2222 |
| Health check ругается на 9001 наружу | Xray слушает не на loopback — проверить профиль в Remnawave |
| Вебхук возвращает 400 | не совпали учётные данные, сумма или валюта — смотреть `payment_events` |

## 18. Security

* Секреты (SSH-ключ, SSH-пароль, токен Remnawave, ключ Yandex, токен Cloudflare)
  шифруются Fernet; ключ живёт только в `.env` и никогда в БД.
* Сообщения с секретами удаляются из чата, обратно секреты не отправляются.
* Логи проходят через редактор-фильтр, который вырезает ключи, токены и заголовки авторизации.
* Пользователю показывается короткая причина ошибки, полный traceback остаётся в логах и
  в `audit_logs`.
* Порт Xray `9001` не открывается наружу ни при каких условиях.
* Вебхуки не доверяют клиентским данным: любой платёж подтверждается запросом к API провайдера.

## 19. Backup

```bash
./scripts/backup.sh dump                     # backups/rwbot-YYYYmmdd-HHMM.sql.gz
./scripts/backup.sh restore backups/<файл>
```

Автоматический бэкап не включён по умолчанию — достаточно добавить вызов `dump` в cron.

## 20. Production deployment

Бот общается с Telegram long polling'ом, поэтому входящий трафик нужен **только** для
колбэков платёжек. Отсюда три варианта.

### Вариант A — Caddy (проще всего, без nginx)

Сертификат Caddy получает и продлевает сам, certbot и cron не нужны:

```bash
echo "BOT_PUBLIC_DOMAIN=bot.example.com" >> .env
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d
```

A-запись домена должна вести на этот сервер, порты 80 и 443 — свободны. Наружу открыты
только `/webhooks/*` и `/healthz`, остальное отдаёт 404.

### Вариант B — Cloudflare Tunnel (совсем без открытых портов)

Подходит, если нет白 IP или не хочется вешать порты наружу:

```bash
cloudflared tunnel login
cloudflared tunnel create rw-cdn-bot
cloudflared tunnel route dns rw-cdn-bot bot.example.com
cloudflared tunnel run --url http://127.0.0.1:8080 rw-cdn-bot
```

TLS терминирует Cloudflare, порт 8080 остаётся на `127.0.0.1`.

### Вариант C — без вебхуков вообще

Пока платежи не подключены (тест, демо, ручные заказы), внешний адрес не нужен совсем:
подними `docker compose up -d` и не публикуй ничего. Бот работает, оплату просто некому
подтвердить. Как только появится мерчант — вернись к A или B.

### Вариант D — nginx вручную

1. Поставить nginx перед ботом и терминировать TLS:

```nginx
location /webhooks/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

2. Порт `8080` наружу не публиковать (в compose он привязан к `127.0.0.1`).
3. `ADMIN_IDS` — только доверенные аккаунты.
4. Хранить `.env` с правами `600`, ключ шифрования — отдельно от бэкапов БД.
5. Следить за `worker`: именно он выполняет все длительные операции.

## Тесты

```bash
pip install -e ".[dev]"
pytest
```

Покрыто: вебхуки платежей, идемпотентность платежей, создание заказа, state machine
deployment'а, клиент Remnawave (включая цепочку получения SECRET_KEY), node installer
(идемпотентность, права на `.env`, legacy-фолбэк, классификация ошибок), клиент Yandex,
проверка DNS, retry, шифрование секретов и редактирование логов, права администратора,
конфигурация nginx и firewall.
