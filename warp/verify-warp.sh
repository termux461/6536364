#!/usr/bin/env bash
# Шаг 4. Проверяем, что сервис поднялся и трафик реально уходит через WARP.
# Логика: сравниваем внешний IP напрямую и через warp-outbound.
# Локальный тест поднимает ВРЕМЕННЫЙ экземпляр Xray на 127.0.0.1:10808
# и после проверки его гасит. Основной конфиг не трогается.
set -euo pipefail

WGCF_DIR="${WGCF_DIR:-/opt/warp}"
OUTBOUND="${OUTBOUND:-$WGCF_DIR/outbound-warp.json}"
PORT="${PORT:-10808}"
XRAY_BIN="${XRAY_BIN:-xray}"
TRACE_URLS=("https://www.cloudflare.com/cdn-cgi/trace" "https://chatgpt.com/cdn-cgi/trace")

echo "===== 1. Состояние сервиса ====="
if systemctl list-unit-files 2>/dev/null | grep -q '^xray\.service'; then
  systemctl is-active xray && systemctl status xray --no-pager -n 15 || true
elif command -v docker >/dev/null; then
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
else
  echo "Ни systemd-юнита xray, ни docker не нашёл — проверьте панель вручную."
fi

echo
echo "===== 2. Внешний IP БЕЗ warp (прямой выход сервера) ====="
DIRECT=$(curl -fsS --max-time 15 "${TRACE_URLS[0]}" | tr -d '\r')
echo "$DIRECT" | grep -E '^(ip|loc|warp)=' || echo "$DIRECT"
DIRECT_IP=$(echo "$DIRECT" | awk -F= '/^ip=/{print $2}')

echo
echo "===== 3. Внешний IP ЧЕРЕЗ warp-outbound ====="
[ -f "$OUTBOUND" ] || { echo "Нет $OUTBOUND — сначала gen-xray-warp.sh" >&2; exit 1; }
command -v "$XRAY_BIN" >/dev/null || {
  echo "xray не в PATH. Если ядро в контейнере, запустите скрипт внутри него:" >&2
  echo "  docker exec -it <container> bash -c 'XRAY_BIN=xray bash -s' < $0" >&2; exit 1; }

TMPCFG=$(mktemp); TMPLOG=$(mktemp)
jq -n --slurpfile ob "$OUTBOUND" --argjson port "$PORT" '{
  log: {loglevel: "warning"},
  inbounds: [{listen: "127.0.0.1", port: $port, protocol: "socks",
              settings: {udp: true}}],
  outbounds: $ob
}' > "$TMPCFG"

"$XRAY_BIN" run -c "$TMPCFG" >"$TMPLOG" 2>&1 &
XPID=$!
cleanup() { kill "$XPID" 2>/dev/null || true; wait "$XPID" 2>/dev/null || true; rm -f "$TMPCFG"; }
trap cleanup EXIT

for i in $(seq 1 20); do
  (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break
  kill -0 "$XPID" 2>/dev/null || { echo "Xray упал:"; cat "$TMPLOG"; exit 1; }
  sleep 0.5
done

WARP_OUT=$(curl -fsS --max-time 25 -x "socks5h://127.0.0.1:$PORT" "${TRACE_URLS[0]}" | tr -d '\r') || {
  echo "Через warp-outbound трафик не пошёл. Лог Xray:"; cat "$TMPLOG"; exit 1; }
echo "$WARP_OUT" | grep -E '^(ip|loc|warp)=' || echo "$WARP_OUT"
WARP_IP=$(echo "$WARP_OUT" | awk -F= '/^ip=/{print $2}')
WARP_FLAG=$(echo "$WARP_OUT" | awk -F= '/^warp=/{print $2}')

echo
echo "===== 4. Маршрутизируемый домен (chatgpt.com) через warp ====="
curl -fsS --max-time 25 -x "socks5h://127.0.0.1:$PORT" "${TRACE_URLS[1]}" \
  | tr -d '\r' | grep -E '^(ip|loc|warp)=' || echo "  chatgpt.com/cdn-cgi/trace недоступен"

echo
echo "===== ИТОГ ====="
echo "Прямой выход : ${DIRECT_IP:-?}"
echo "Через WARP   : ${WARP_IP:-?}  (warp=${WARP_FLAG:-?})"
if [ -n "${WARP_IP:-}" ] && [ "${WARP_IP:-}" != "${DIRECT_IP:-}" ]; then
  echo "OK: IP отличается — туннель работает."
  [ "${WARP_FLAG:-}" = "on" ] || [ "${WARP_FLAG:-}" = "plus" ] \
    && echo "OK: Cloudflare подтверждает warp=${WARP_FLAG}." \
    || echo "ВНИМАНИЕ: warp=${WARP_FLAG:-?} — проверьте reserved/ключи."
else
  echo "ПРОБЛЕМА: IP совпадает с прямым — трафик мимо WARP. Лог Xray:"
  sed -n '1,40p' "$TMPLOG"
fi
rm -f "$TMPLOG"
