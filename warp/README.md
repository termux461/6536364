# WARP на выходе: подключаем

Комплект скриптов для вывода части трафика (OpenAI, Spotify, Netflix) через
Cloudflare WARP как отдельный outbound Xray. Всё идемпотентно: повторный
запуск не плодит дубли и не затирает конфиг без бэкапа.

## Порядок запуска

Всё выполняется **на сервере, от root**, в каталоге `warp/` этого репозитория.

| # | Команда | Что делает | Как проверить |
|---|---------|-----------|---------------|
| 1 | `./get-wgcf.sh` | Ставит `wgcf`, регистрирует аккаунт WARP, генерирует `wgcf-profile.conf` | В выводе есть `PrivateKey` и два `Address` (v4 + v6) |
| 2 | `./gen-xray-warp.sh` | Читает профиль и собирает `outbound-warp.json` с реальными ключами | Показан JSON с `"tag": "warp"`, `secretKey` скрыт |
| 3 | `./apply-warp.sh [/путь/config.json]` | Вклеивает outbound + правило маршрутизации в конфиг Xray | Печатает список тегов outbound и первые правила |
| 4 | перезапуск ядра | `systemctl restart xray` / `marzban restart` / `docker compose restart` | Сервис active (running) |
| 5 | `./verify-warp.sh` | Сравнивает внешний IP напрямую и через WARP | «Через WARP» ≠ «Прямой выход», `warp=on` |
| 6 | `./warp-plus.sh <КЛЮЧ>` *(опц.)* | Привязывает лицензию WARP+ | В `wgcf-account.toml` виден `premium_data` |

После шага 6 повторите шаги 2 → 3 → 4, чтобы Xray подхватил обновлённый профиль.

Рабочий каталог по умолчанию — `/opt/warp` (меняется переменной `WGCF_DIR`).

## Настройки через переменные окружения

```bash
WGCF_DIR=/opt/warp          # где лежат wgcf-account.toml / wgcf-profile.conf
ENDPOINT=162.159.192.1:2408 # IP-литерал, чтобы не зависеть от DNS
MTU=1280                    # при потерях/зависаниях пробуйте 1400 или 1200
XRAY_CONFIG=/usr/local/etc/xray/config.json
DRY_RUN=1 ./apply-warp.sh   # показать diff и ничего не менять
```

`apply-warp.sh` без аргумента сам ищет конфиг в типовых местах: standalone Xray,
Marzban (`/var/lib/marzban/xray_config.json`), Remnawave, x-ui.

## Что именно вставляется

**Outbound** (`gen-xray-warp.sh` подставляет `secretKey` и `address` из вашего
профиля — никаких вымышленных значений):

```json
{
  "tag": "warp",
  "protocol": "wireguard",
  "settings": {
    "secretKey": "<PrivateKey из wgcf-profile.conf>",
    "address": ["172.16.0.2/32", "<IPv6 из wgcf-profile.conf>/128"],
    "peers": [{
      "publicKey": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
      "endpoint": "162.159.192.1:2408"
    }],
    "mtu": 1280,
    "reserved": [0, 0, 0],
    "noKernelTun": true
  }
}
```

`publicKey` — публичный ключ пира Cloudflare, он одинаков для всех аккаунтов
WARP, его подставлять не нужно. `reserved: [0,0,0]` верно для профилей `wgcf`;
ненулевые значения нужны только для Zero Trust с client ID.

**Правило маршрутизации** (`routing-rule-warp.json`) вставляется **первым** в
`routing.rules` — иначе его перекроет catch-all правило на `direct`:

```json
{
  "type": "field",
  "outboundTag": "warp",
  "domain": ["geosite:openai", "domain:chatgpt.com", "domain:oaistatic.com",
             "domain:spotify.com", "domain:scdn.co", "geosite:netflix"]
}
```

`geosite:openai` и `geosite:netflix` требуют актуального `geosite.dat` рядом с
ядром. Если категории не найдены — Xray скажет об этом при `xray run -test`;
обновите geo-файлы или оставьте только `domain:`-записи.

## Про ошибку rp_filter

```
failed to disable ipv4 rp_filter for all:
open /proc/sys/net/ipv4/conf/all/rp_filter: read-only file system
```

Это **предупреждение, а не падение**. Xray пытается отключить reverse path
filtering для режима с ядерным TUN-интерфейсом, а в контейнере `/proc/sys`
смонтирован read-only.

С `"noKernelTun": true` ядерный TUN не используется вовсе — WireGuard работает
в userspace-стеке, и sysctl ему не нужен. Строку в логе можно игнорировать;
проверяйте не её, а результат `verify-warp.sh`.

Если хотите убрать её совсем — дайте контейнеру права (docker-compose):

```yaml
services:
  xray:
    cap_add: [NET_ADMIN]
    sysctls:
      net.ipv4.conf.all.rp_filter: 0
```

Обратная ситуация: если ваш Xray-core старый и ругается на неизвестное поле
`noKernelTun` — уберите эту строку из outbound, тогда потребуются `NET_ADMIN`
и доступ к sysctl.

## Проверка, что трафик реально идёт через WARP

`verify-warp.sh` поднимает **временный** экземпляр Xray на `127.0.0.1:10808`
только с warp-outbound (основной конфиг не трогает), затем сравнивает:

```
Прямой выход : 203.0.113.10
Через WARP   : 104.28.x.x   (warp=on)
```

Разные IP + `warp=on` от самого Cloudflare = туннель работает. Дополнительно
скрипт дёргает `https://chatgpt.com/cdn-cgi/trace` — это домен из списка
маршрутизации, и он отдаёт тот же trace-эндпоинт.

Проверка с клиента (после перезапуска ядра), должна показать WARP-адрес:

```bash
curl -x socks5h://127.0.0.1:<порт_вашего_клиента> https://chatgpt.com/cdn-cgi/trace
```

## Откат

`apply-warp.sh` перед каждой правкой кладёт рядом `config.json.bak.<дата>`:

```bash
cp -a /usr/local/etc/xray/config.json.bak.<дата> /usr/local/etc/xray/config.json
systemctl restart xray
```

## Безопасность

`wgcf-account.toml` и `wgcf-profile.conf` содержат приватный ключ WireGuard —
скрипты выставляют им права `600`. Не коммитьте их и не публикуйте в чатах;
`.gitignore` в этом каталоге их уже исключает.
