-- =====================================================================================
--  Migración v2 · para una base creada con la versión anterior (sin borrar datos)
--  Estados aplazado, créditos, Precio Justo e imagen de eventos.
--  Uso:  bash scripts/migrar.sh      (o ejecútalo como root en MySQL Workbench / Adminer)
--  Es seguro ejecutarlo más de una vez.
-- =====================================================================================

-- Eventos: nuevo estado e imagen
ALTER TABLE esquema_eventos.evento
  MODIFY estado ENUM('programado','aplazado','realizado','cancelado') NOT NULL DEFAULT 'programado';
CREATE TABLE IF NOT EXISTS esquema_eventos.imagen_evento (
    id_evento   INT         NOT NULL PRIMARY KEY,
    tipo_mime   VARCHAR(40) NOT NULL,
    datos       MEDIUMBLOB  NOT NULL,
    actualizada DATETIME    NOT NULL,
    CONSTRAINT fk_imagen_evento FOREIGN KEY (id_evento) REFERENCES esquema_eventos.evento (id_evento) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Pagos: tabla de créditos (las columnas nuevas de pago van en v2_pagos.sql)
CREATE TABLE IF NOT EXISTS esquema_pagos.credito (
    id_credito    INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario    INT           NOT NULL,
    tipo          ENUM('abono','uso') NOT NULL,
    concepto      ENUM('evento_cancelado','precio_justo','pago_compra') NOT NULL,
    monto         DECIMAL(12,2) NOT NULL,
    id_referencia INT           NOT NULL,
    descripcion   VARCHAR(255)  NOT NULL,
    fecha         DATETIME      NOT NULL,
    CONSTRAINT ck_credito_monto CHECK (monto > 0),
    INDEX ix_credito_id_usuario (id_usuario),
    INDEX ix_credito_id_referencia (id_referencia)
) ENGINE=InnoDB;

-- Notificaciones: nuevos tipos
ALTER TABLE esquema_notificaciones.notificacion
  MODIFY tipo ENUM('reserva','pago','expiracion','evento','credito') NOT NULL;
