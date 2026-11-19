-- Microservicio de Eventos · Tabla 51 (+ estado 'aplazado' e IMAGEN_EVENTO)
-- id_escenario es referencia lógica (RL) a esquema_escenarios.escenario: la valida el servicio.
USE esquema_eventos;

CREATE TABLE IF NOT EXISTS evento (
    id_evento    INT AUTO_INCREMENT PRIMARY KEY,
    id_escenario INT          NOT NULL,
    nombre       VARCHAR(120) NOT NULL,
    descripcion  TEXT,
    fecha        DATE         NOT NULL,
    hora         TIME         NOT NULL,
    -- programado → aplazado (cambió la fecha) → cancelado (reactivable) / realizado (final)
    estado       ENUM('programado','aplazado','realizado','cancelado') NOT NULL DEFAULT 'programado',
    INDEX ix_evento_id_escenario (id_escenario),
    INDEX ix_evento_estado_fecha (estado, fecha)
) ENGINE=InnoDB;

-- Imagen (póster) subida por el administrador; tabla aparte para que listar eventos sea liviano.
CREATE TABLE IF NOT EXISTS imagen_evento (
    id_evento   INT         NOT NULL PRIMARY KEY,
    tipo_mime   VARCHAR(40) NOT NULL,
    datos       MEDIUMBLOB  NOT NULL,
    actualizada DATETIME    NOT NULL,
    CONSTRAINT fk_imagen_evento FOREIGN KEY (id_evento) REFERENCES evento (id_evento) ON DELETE CASCADE
) ENGINE=InnoDB;
