-- =====================================================================================
--  Sistema de Gestión de Boletería para Eventos · Universidad Central · BD Avanzadas
--  Un esquema (database de MySQL) por microservicio. Modelo relacional: Tablas 48 a 60.
--  docker-compose ejecuta los scripts de esta carpeta en orden alfabético la primera vez.
-- =====================================================================================
CREATE DATABASE IF NOT EXISTS esquema_usuarios       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_acceso         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_escenarios     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_eventos        CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_localidades    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_asientos       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_disponibilidad CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_reservas       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_compras        CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_pagos          CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_boletas        CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_notificaciones CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_auditoria      CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS esquema_analitica      CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;  -- Data Warehouse

-- El usuario 'boleteria' lo crea docker-compose (MYSQL_USER). Si cambias el nombre, ajústalo aquí.
GRANT ALL PRIVILEGES ON esquema_usuarios.*       TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_acceso.*         TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_escenarios.*     TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_eventos.*        TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_localidades.*    TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_asientos.*       TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_disponibilidad.* TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_reservas.*       TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_compras.*        TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_pagos.*          TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_boletas.*        TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_notificaciones.* TO 'boleteria'@'%';
-- RN19: la aplicación solo puede consultar e insertar en la auditoría (sin UPDATE ni DELETE)
GRANT SELECT, INSERT, CREATE, INDEX, REFERENCES ON esquema_auditoria.* TO 'boleteria'@'%';
GRANT ALL PRIVILEGES ON esquema_analitica.*      TO 'boleteria'@'%';
FLUSH PRIVILEGES;
