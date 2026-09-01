#!/usr/bin/env bash
# Шаг 1. Установка wgcf, регистрация аккаунта Cloudflare WARP и генерация профиля.
# Идемпотентно: повторный запуск не перезатирает существующий wgcf-account.toml.
set -euo pipefail

WGCF_DIR="${WGCF_DIR:-/opt/warp}"
WGCF_BIN="${WGCF_BIN:-/usr/bin/wgcf}"

case "$(uname -m)" in
  x86_64|amd64)   ARCH=amd64 ;;
  aarch64|arm64)  ARCH=arm64 ;;
  armv7l)         ARCH=armv7 ;;
  *) echo "Неизвестная архитектура: $(uname -m)" >&2; exit 1 ;;
esac

echo "==> Архитектура: linux_${ARCH}"

if [ ! -x "$WGCF_BIN" ]; then
  # Тег последнего релиза берём через redirect /releases/latest — не упирается
  # в rate limit api.github.com и не ломается при смене формата JSON.
  TAG=$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        https://github.com/ViRb3/wgcf/releases/latest | sed 's#.*/tag/##')
  [ -n "$TAG" ] || { echo "Не удалось определить версию wgcf" >&2; exit 1; }
  VER="${TAG#v}"
  URL="https://github.com/ViRb3/wgcf/releases/download/${TAG}/wgcf_${VER}_linux_${ARCH}"
  echo "==> Качаю $URL"
  curl -fsSL -o "$WGCF_BIN" "$URL"
  chmod +x "$WGCF_BIN"
else
  echo "==> wgcf уже установлен, пропускаю загрузку"
fi

"$WGCF_BIN" --version || true

mkdir -p "$WGCF_DIR"
cd "$WGCF_DIR"

if [ -f wgcf-account.toml ]; then
  echo "==> wgcf-account.toml уже есть — регистрацию пропускаю"
else
  echo "==> Регистрирую новый аккаунт WARP (ToS принимается флагом)"
  "$WGCF_BIN" register --accept-tos
fi

echo "==> Генерирую wgcf-profile.conf"
"$WGCF_BIN" generate

echo
echo "===== wgcf-profile.conf ====="
cat wgcf-profile.conf
echo "============================="
echo
echo "Файлы лежат в: $WGCF_DIR"
echo "ВАЖНО: wgcf-account.toml и wgcf-profile.conf содержат приватный ключ — не публикуйте их."
chmod 600 wgcf-account.toml wgcf-profile.conf 2>/dev/null || true
