#!/usr/bin/env bash
# RNF05 · Restaura un respaldo:  bash scripts/restore.sh backups/boleteria_XXXX.sql
set -e
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
[ -f "$1" ] || { echo "Uso: bash scripts/restore.sh backups/archivo.sql"; exit 1; }
docker compose exec -T mysql mysql -uroot -p"${MYSQL_ROOT_PASSWORD:-root_pass}" < "$1"
echo "Restaurado: $1"
