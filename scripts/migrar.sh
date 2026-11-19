#!/usr/bin/env bash
# Actualiza una base de datos creada con la versión anterior, sin borrar datos.
# Uso:  bash scripts/migrar.sh
set -e
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
SQL="docker compose exec -T mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD:-root_pass}"
falta() { $SQL -N -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='$1' AND table_name='$2' AND column_name='$3'" 2>/dev/null | grep -q '^0$'; }
$SQL < database/migraciones/v2_estados_creditos_imagenes.sql
if falta esquema_pagos pago metodo; then $SQL < database/migraciones/v2_pagos.sql; fi
if falta esquema_boletas boleta vigente_unica; then $SQL < database/migraciones/v2_boletas.sql; fi
$SQL < database/migraciones/v3_analitica.sql
docker compose up -d --build analitica   # crea sus tablas al iniciar (AUTO_CREATE_TABLES)
docker compose restart
echo "Migración aplicada. Los servicios se reiniciaron."
