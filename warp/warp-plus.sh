#!/usr/bin/env bash
# Шаг 5 (опционально). Привязка ключа WARP+ к существующему аккаунту.
# Требует уже созданный wgcf-account.toml (см. get-wgcf.sh).
set -euo pipefail

WGCF_DIR="${WGCF_DIR:-/opt/warp}"
WGCF_BIN="${WGCF_BIN:-/usr/bin/wgcf}"
LICENSE_KEY="${1:-${WARP_LICENSE_KEY:-}}"

if [ -z "$LICENSE_KEY" ]; then
  echo "Использование: $0 <WARP_PLUS_LICENSE_KEY>" >&2
  echo "Ключ берётся в приложении 1.1.1.1: Settings -> Account -> Key." >&2
  exit 2
fi

cd "$WGCF_DIR"
[ -f wgcf-account.toml ] || { echo "Нет $WGCF_DIR/wgcf-account.toml — сначала запустите get-wgcf.sh" >&2; exit 1; }

cp -a wgcf-account.toml "wgcf-account.toml.bak.$(date +%Y%m%d%H%M%S)"

echo "==> Применяю лицензионный ключ"
"$WGCF_BIN" update --license-key "$LICENSE_KEY"

echo "==> Перегенерирую профиль"
"$WGCF_BIN" generate

echo "==> Тип аккаунта / квота:"
grep -E 'account_type|premium_data|license_key' wgcf-account.toml | sed 's/license_key.*/license_key = <скрыт>/'

echo
echo "Приватный ключ при смене лицензии НЕ меняется, но адреса могли обновиться."
echo "Перезапустите gen-xray-warp.sh + apply-warp.sh, чтобы конфиг Xray подхватил новый профиль."
