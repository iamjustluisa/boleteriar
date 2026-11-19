-- v3 (Sprints 7 y 8): Data Warehouse del microservicio de Analítica y permiso de indicadores.
CREATE DATABASE IF NOT EXISTS esquema_analitica CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON esquema_analitica.* TO 'boleteria'@'%';
FLUSH PRIVILEGES;
INSERT IGNORE INTO esquema_acceso.permiso (nombre, descripcion)
  VALUES ('consultar_indicadores', 'Consultar indicadores y ejecutar el ETL del Data Warehouse');
INSERT IGNORE INTO esquema_acceso.rol_permiso (id_rol, id_permiso)
  SELECT r.id_rol, p.id_permiso FROM esquema_acceso.rol r JOIN esquema_acceso.permiso p
  WHERE r.nombre = 'administrador' AND p.nombre = 'consultar_indicadores';
