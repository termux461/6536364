#!/usr/bin/env bash
# PostgreSQL backup / restore helper.
#   ./scripts/backup.sh dump              -> backups/rwbot-YYYYmmdd-HHMM.sql.gz
#   ./scripts/backup.sh restore <file>
set -euo pipefail

SERVICE=postgres
DB="${POSTGRES_DB:-rwbot}"
USER="${POSTGRES_USER:-rwbot}"
DIR="$(dirname "$0")/../backups"
mkdir -p "$DIR"

case "${1:-dump}" in
  dump)
    OUT="$DIR/rwbot-$(date +%Y%m%d-%H%M).sql.gz"
    docker compose exec -T "$SERVICE" pg_dump -U "$USER" "$DB" | gzip >"$OUT"
    echo "written: $OUT"
    ;;
  restore)
    [ -n "${2:-}" ] || { echo "usage: $0 restore <file.sql.gz>"; exit 1; }
    gunzip -c "$2" | docker compose exec -T "$SERVICE" psql -U "$USER" -d "$DB"
    echo "restored from $2"
    ;;
  *)
    echo "usage: $0 {dump|restore <file>}"; exit 1
    ;;
esac
