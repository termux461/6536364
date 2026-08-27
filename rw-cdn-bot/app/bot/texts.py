"""All user-facing copy in one place."""
from __future__ import annotations

from app.services.remnawave.templates import XHTTP_PATH

START = (
    "🚀 <b>Автоматическая настройка Remnawave + Yandex CDN</b>\n\n"
    "Бот самостоятельно настроит Origin Server,\n"
    "Remnawave, XHTTP и Yandex Cloud CDN.\n\n"
    "Вам не придётся вручную выполнять десятки команд."
)

HOW_IT_WORKS = (
    "📖 <b>Как это работает</b>\n\n"
    "1. Вы оплачиваете настройку.\n"
    "2. Бот спрашивает данные: панель Remnawave, Origin Server, домены и доступ к Yandex Cloud.\n"
    "3. Бот подключается к Origin Server по SSH и готовит его: пакеты, Docker, Nginx, firewall, BBR, swap.\n"
    "4. Выпускает SSL для Origin Domain через Let's Encrypt.\n"
    "5. Создаёт в Remnawave профиль <code>cdn</code>, Remnawave Node и Host.\n"
    "6. Устанавливает Remnanode на Origin Server.\n"
    "7. Создаёт сертификат в Yandex Certificate Manager и ресурс Yandex Cloud CDN.\n"
    "8. Получает CNAME от Yandex и настраивает DNS.\n"
    "9. Проверяет DNS, CDN, XHTTP и делает финальный health check.\n\n"
    "<b>Итоговая схема:</b>\n"
    "<code>Клиент → CDN Domain → Yandex Cloud CDN → Origin Domain →\n"
    f"Origin Server → Nginx :443 → 127.0.0.1:2090 → Remnawave Node / Xray</code>\n\n"
    f"Путь XHTTP: <code>{XHTTP_PATH}</code>"
)

REQUIREMENTS = (
    "📋 <b>Что понадобится</b>\n\n"
    "• Origin Server (Ubuntu/Debian) с root-доступом по SSH\n"
    "• Origin Domain и CDN Domain (разные поддомены)\n"
    "• Доступ к DNS домена\n"
    "• URL панели Remnawave и API-токен\n"
    "• Yandex Cloud: Folder ID и ключ сервисного аккаунта\n"
    "• Email для Let's Encrypt"
)

CHOOSE_PAYMENT = "Выберите способ оплаты:"
PAYMENT_CREATED = (
    "💳 <b>Счёт создан</b>\n\n"
    "Сумма: {amount}\n\n"
    "Оплатите по ссылке ниже. Настройка запустится автоматически "
    "после подтверждения платежа платёжной системой."
)

ASK_PANEL_URL = (
    "Введите URL панели Remnawave:\n\n"
    "Например:\n<code>https://panel.example.com</code>"
)
ASK_PANEL_TOKEN = "Введите Remnawave API Token:"
ASK_ORIGIN_IP = "Введите IP Origin Server:"
ASK_SSH_PORT = "Введите SSH порт:\n\nПо умолчанию: <code>2222</code>"
ASK_SSH_USER = "Введите SSH username:\n\nНапример: <code>root</code>"
ASK_SSH_AUTH = (
    "Как подключаться к Origin Server?\n\n"
    "Рекомендуется SSH-ключ. Пароль допускается как запасной вариант."
)
ASK_SSH_KEY = (
    "Отправьте приватный SSH-ключ одним сообщением или файлом.\n\n"
    "Ключ будет зашифрован и никогда не будет отправлен обратно."
)
ASK_SSH_PASSWORD = "Введите SSH пароль:"
ASK_ORIGIN_DOMAIN = "Введите Origin Domain:\n\nНапример: <code>origin.example.com</code>"
ASK_CDN_DOMAIN = "Введите CDN Domain:\n\nНапример: <code>cdn.example.com</code>"
ASK_EMAIL = "Введите email для Let's Encrypt:"
ASK_YANDEX_CLOUD_ID = "Введите Yandex Cloud ID:"
ASK_YANDEX_FOLDER_ID = "Введите Yandex Folder ID:"
ASK_YANDEX_KEY = (
    "Отправьте JSON-ключ сервисного аккаунта Yandex Cloud (файлом или текстом).\n\n"
    "Рекомендуется сервисный аккаунт с минимальными правами: "
    "<code>cdn.editor</code>, <code>certificate-manager.editor</code>, "
    "<code>dns.editor</code> (если DNS в Yandex)."
)
ASK_DNS_MODE = (
    "Как управлять DNS?\n\n"
    "Если у вас есть API-токен Cloudflare — бот создаст записи сам. "
    "Иначе бот покажет, что добавить вручную."
)
ASK_CLOUDFLARE_TOKEN = "Отправьте API-токен Cloudflare с правами Zone.DNS:Edit:"

DATA_SAVED = "✅ Данные сохранены. Запускаю настройку…"
SECRET_RECEIVED = "🔒 Принято и зашифровано."
PANEL_VERSION_DETECTED = "🧩 Панель определена: {version}."
PANEL_VERSION_UNKNOWN = (
    "🧩 Версию панели определить не удалось ({reason}) — она будет определена при настройке."
)

MANUAL_DNS = (
    "☁️ <b>Нужна DNS-запись</b>\n\n"
    "Тип: <code>{record_type}</code>\n"
    "Имя: <code>{name}</code>\n"
    "Значение: <code>{value}</code>\n\n"
    "Проксирование должно быть выключено (у Cloudflare — серое облако, DNS only).\n\n"
    "После добавления нажмите «Проверить DNS»."
)

DNS_OK = "🟢 DNS успешно настроен. Продолжаю настройку…"
DNS_NOT_YET = "🟠 Запись пока не видна публичным резолверам. Попробуйте через пару минут."

SUPPORT = "🆘 Поддержка: @{username}\n\nНапишите номер заказа — так мы ответим быстрее."
NO_ORDERS = "У вас пока нет заказов."
BLOCKED = "Доступ к боту ограничен."
ORDER_ACTIVE = "У вас уже есть активный заказ. Дождитесь его завершения."


ASK_YANDEX_AUTH_MODE = (
    "Как бот будет подключаться к вашему Yandex Cloud?\n\n"
    "🔑 <b>Ключ сервисного аккаунта</b> — рекомендуется. Работает бессрочно, права ограничены "
    "ролями <code>cdn.editor</code>, <code>certificate-manager.editor</code>, "
    "<code>dns.editor</code>.\n\n"
    "🎫 <b>OAuth-токен</b> — проще получить, живёт год.\n\n"
    "🍪 <b>Cookie браузера</b> — cookie используются только на время настройки и удаляются "
    "сразу после неё."
)

ASK_YANDEX_OAUTH = (
    "Пришлите OAuth-токен Yandex.\n\n"
    "Получить: откройте страницу выдачи токена для Yandex Cloud, нажмите «Разрешить» и "
    "скопируйте значение. Токен начинается с <code>y0_</code> и живёт год.\n\n"
    "Сообщение будет удалено сразу после сохранения."
)

ASK_YANDEX_COOKIES = (
    "Пришлите cookie — строкой или файлом.\n\n"
    "Принимаются:\n"
    "• строка из DevTools → Network → запрос к консоли → заголовок <code>Cookie</code>\n"
    "• файл <code>.cookie</code> / <code>cookies.txt</code> (формат Netscape)\n"
    "• файл <code>.json</code> из EditThisCookie, Cookie-Editor или Playwright\n\n"
    "Снимать нужно на вкладке с <b>консолью Yandex Cloud</b> — внутри должно быть "
    "<code>yc_session</code>. Cookie Яндекс ID (<code>Session_id</code> с yandex.ru) "
    "не подойдут: это другая сессия.\n\n"
    "Cookie нигде не сохраняются: они используются для настройки и удаляются сразу после неё. "
    "Сообщение будет удалено."
)

YANDEX_AUTH_OK = "✅ Доступ к Yandex Cloud проверен."
YANDEX_AUTH_FAILED = (
    "❌ Не удалось подключиться к Yandex Cloud с этими данными:\n<code>{reason}</code>\n\n"
    "Проверьте и пришлите заново."
)
YANDEX_REAUTH_NEEDED = (
    "⏸ Настройка заказа #{order_id} на паузе — нужен доступ к Yandex Cloud.\n\n"
    "Пришлите данные командой /reauth {order_id}, настройка продолжится с того же места."
)


YANDEX_ACCESS_DENIED = (
    "❌ Подключение к Yandex Cloud работает, но прав не хватает:\n\n"
    "<code>{details}</code>\n\n"
    "Выдайте роли на <b>каталог</b> (Folder), где будет жить CDN, и пришлите данные заново."
)


YANDEX_CHECK_FAILED = (
    "❌ Не удалось обратиться к Yandex Cloud с этими данными:\n\n"
    "<code>{reason}</code>\n\n"
    "Это не про права — запрос вообще не дошёл. Проверьте данные или выберите другой способ "
    "авторизации: 🎫 OAuth-токен работает от того же аккаунта и настраивается за минуту."
)


PICK_CLOUD = "Выберите облако:"
PICK_FOLDER = "Выберите каталог, в котором будет жить CDN:"

SCOPE_RESOLVED = (
    "✅ Определено автоматически:\n"
    "Cloud ID: <code>{cloud}</code>\n"
    "Каталог: <code>{folder}</code>"
)

ROLES_GRANTED = "✅ Недостающие роли выданы автоматически: <code>{roles}</code>"

ASK_YANDEX_LOGIN = (
    "Пришлите ваш логин Yandex (например <code>ivan.petrov</code>) — он нужен только чтобы "
    "выдать недостающие роли на каталог. Для авторизации логин не используется.\n\n"
    "Если не хотите — выдайте роли вручную в консоли и пришлите данные заново."
)
