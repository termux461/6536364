#!/usr/bin/env bash
# Шаг 2. Из wgcf-profile.conf собираем outbound "warp" для Xray.
# Никаких выдуманных значений: PrivateKey и Address читаются из профиля.
set -euo pipefail

WGCF_DIR="${WGCF_DIR:-/opt/warp}"
PROFILE="${PROFILE:-$WGCF_DIR/wgcf-profile.conf}"
OUT="${OUT:-$WGCF_DIR/outbound-warp.json}"
# Публичный ключ пира Cloudflare — константа, одинаковая для всех WARP-аккаунтов.
PEER_PUBKEY="${PEER_PUBKEY:-bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=}"
# IP-литерал вместо engage.cloudflareclient.com, чтобы не зависеть от DNS.
ENDPOINT="${ENDPOINT:-162.159.192.1:2408}"
MTU="${MTU:-1280}"

[ -f "$PROFILE" ] || { echo "Нет профиля $PROFILE — сначала запустите get-wgcf.sh" >&2; exit 1; }

# В [Interface] может быть либо две строки Address, либо одна через запятую.
PRIVKEY=$(awk -F'=' '/^[[:space:]]*PrivateKey[[:space:]]*=/ {sub(/^[^=]*=[[:space:]]*/,""); print; exit}' "$PROFILE")
ADDRS=$(awk '/^[[:space:]]*\[Peer\]/{exit}
             /^[[:space:]]*Address[[:space:]]*=/ {sub(/^[^=]*=[[:space:]]*/,""); gsub(/[[:space:]]/,""); print}' "$PROFILE" \
        | tr ',' '\n' | grep -v '^$')

V4=$(echo "$ADDRS" | grep -v ':' | head -1)
V6=$(echo "$ADDRS" | grep ':'    | head -1)

[ -n "$PRIVKEY" ] || { echo "Не нашёл PrivateKey в $PROFILE" >&2; exit 1; }
[ -n "$V4" ]      || { echo "Не нашёл IPv4 Address в $PROFILE" >&2; exit 1; }
if [ -z "$V6" ]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: в профиле нет IPv6-адреса, собираю outbound только с IPv4." >&2
  ADDR_JSON="\"$V4\""
else
  ADDR_JSON="\"$V4\", \"$V6\""
fi

cat > "$OUT" <<JSON
{
  "tag": "warp",
  "protocol": "wireguard",
  "settings": {
    "secretKey": "$PRIVKEY",
    "address": [$ADDR_JSON],
    "peers": [
      {
        "publicKey": "$PEER_PUBKEY",
        "endpoint": "$ENDPOINT"
      }
    ],
    "mtu": $MTU,
    "reserved": [0, 0, 0],
    "noKernelTun": true
  }
}
JSON

chmod 600 "$OUT"
echo "==> Готов outbound: $OUT"
sed 's/\("secretKey": "\)[^"]*"/\1<скрыт>"/' "$OUT"
