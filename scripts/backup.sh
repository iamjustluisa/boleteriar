#!/usr/bin/env bash
# RNF05 · Respaldo de los 13 esquemas (incluye triggers) en backups/boleteria_<fecha>.sql
set -e
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
ARCHIVO="backups/boleteria_$(date +%Y%m%d_%H%M%S).sql"
ESQUEMAS="esquema_usuarios esquema_acceso esquema_escenarios esquema_eventos esquema_localidades esquema_asientos esquema_disponibilidad esquema_reservas esquema_compras esquema_pagos esquema_boletas esquema_notificaciones esquema_auditoria esquema_analitica"
docker compose exec -T mysql mysqldump -uroot -p"${MYSQL_ROOT_PASSWORD:-root_pass}" \
  --single-transaction --routines --triggers --databases $ESQUEMAS > "$ARCHIVO"
echo "Respaldo creado: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"
