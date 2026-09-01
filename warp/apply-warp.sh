#!/usr/bin/env bash
# Шаг 3. Вклеиваем outbound "warp" и правило маршрутизации в конфиг Xray.
# Идемпотентно: старые записи с тегом warp удаляются перед вставкой.
# Ничего не перезаписывает без бэкапа и без проверки синтаксиса.
set -euo pipefail

WGCF_DIR="${WGCF_DIR:-/opt/warp}"
OUTBOUND="${OUTBOUND:-$WGCF_DIR/outbound-warp.json}"
RULE="${RULE:-$(dirname "$0")/routing-rule-warp.json}"
DRY_RUN="${DRY_RUN:-0}"

# Путь к конфигу: аргумент, переменная XRAY_CONFIG, либо автопоиск.
CONFIG="${1:-${XRAY_CONFIG:-}}"
if [ -z "$CONFIG" ]; then
  for c in /usr/local/etc/xray/config.json \
           /etc/xray/config.json \
           /var/lib/marzban/xray_config.json \
           /opt/remnanode/config.json \
           /etc/x-ui/config.json; do
    [ -f "$c" ] && { CONFIG="$c"; break; }
  done
fi
[ -n "$CONFIG" ] && [ -f "$CONFIG" ] || {
  echo "Не нашёл config.json Xray. Укажите путь: $0 /путь/к/config.json" >&2; exit 1; }

command -v jq >/dev/null || { echo "Нужен jq: apt-get install -y jq" >&2; exit 1; }
[ -f "$OUTBOUND" ] || { echo "Нет $OUTBOUND — сначала запустите gen-xray-warp.sh" >&2; exit 1; }
[ -f "$RULE" ]     || { echo "Нет $RULE" >&2; exit 1; }

jq -e . "$CONFIG" >/dev/null || { echo "$CONFIG — невалидный JSON, правьте вручную" >&2; exit 1; }

echo "==> Конфиг: $CONFIG"
BACKUP="${CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
cp -a "$CONFIG" "$BACKUP"
echo "==> Бэкап: $BACKUP"

TMP=$(mktemp)
jq --slurpfile ob "$OUTBOUND" --slurpfile rl "$RULE" '
  # 1. outbounds: выкидываем прежний warp, добавляем свежий в конец
  .outbounds = ((.outbounds // []) | map(select(.tag != "warp"))) + $ob
  # 2. routing: правило warp должно стоять ПЕРЕД catch-all правилами
  | .routing = (.routing // {})
  | .routing.domainStrategy = (.routing.domainStrategy // "IPIfNonMatch")
  | .routing.rules = $rl + ((.routing.rules // []) | map(select(.outboundTag != "warp")))
' "$CONFIG" > "$TMP"

jq -e . "$TMP" >/dev/null || { echo "Получился невалидный JSON, изменения не применены" >&2; rm -f "$TMP"; exit 1; }

if [ "$DRY_RUN" = "1" ]; then
  echo "==> DRY_RUN=1, показываю diff и выхожу"
  diff <(jq -S . "$CONFIG") <(jq -S . "$TMP") || true
  rm -f "$TMP"; exit 0
fi

# Проверка конфига самим Xray, если бинарь доступен
if command -v xray >/dev/null; then
  echo "==> xray -test"
  if ! xray run -test -c "$TMP"; then
    echo "Xray забраковал конфиг — откатываюсь, оригинал не тронут" >&2
    rm -f "$TMP"; exit 1
  fi
else
  echo "==> xray в PATH нет (вероятно, он в контейнере) — пропускаю offline-проверку"
fi

cat "$TMP" > "$CONFIG"
rm -f "$TMP"
echo "==> Конфиг обновлён"

echo "==> Проверка результата:"
jq '{outbound_tags: [.outbounds[].tag], first_rules: [.routing.rules[0:2][] | {outboundTag, domain}]}' "$CONFIG"

echo
echo "Теперь перезапустите панель/ядро, например:"
echo "  systemctl restart xray        # standalone Xray"
echo "  marzban restart               # Marzban"
echo "  docker compose restart        # docker-развёртывание (из каталога с compose-файлом)"
echo "Откат: cp -a $BACKUP $CONFIG && перезапуск"
