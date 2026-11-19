-- Microservicio de Auditoría · Tabla 60
-- RN19: los registros no se modifican ni se eliminan. Además de no conceder UPDATE/DELETE al
-- usuario de la aplicación (00_crear_esquemas.sql), estos triggers lo impiden para cualquiera.
USE esquema_auditoria;

CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario   INT          NULL,                   -- RL -> Usuarios
    accion       VARCHAR(60)  NOT NULL,
    entidad      VARCHAR(60)  NOT NULL,
    id_entidad   INT          NULL,
    fecha_hora   DATETIME     NOT NULL,
    detalle      VARCHAR(255) NULL,
    INDEX ix_auditoria_id_usuario (id_usuario),
    INDEX ix_auditoria_accion (accion),
    INDEX ix_auditoria_fecha_hora (fecha_hora)
) ENGINE=InnoDB;

DROP TRIGGER IF EXISTS trg_auditoria_sin_update;
DROP TRIGGER IF EXISTS trg_auditoria_sin_delete;
DELIMITER $$
CREATE TRIGGER trg_auditoria_sin_update BEFORE UPDATE ON auditoria FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'RN19: los registros de auditoria no se pueden modificar';
END$$
CREATE TRIGGER trg_auditoria_sin_delete BEFORE DELETE ON auditoria FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'RN19: los registros de auditoria no se pueden eliminar';
END$$
DELIMITER ;
