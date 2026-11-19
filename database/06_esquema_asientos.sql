-- Microservicio de Asientos · Tabla 53
USE esquema_asientos;

CREATE TABLE IF NOT EXISTS asiento (
    id_asiento   INT AUTO_INCREMENT PRIMARY KEY,
    id_localidad INT        NOT NULL,                 -- RL -> Localidades
    fila         VARCHAR(5) NOT NULL,
    numero       INT        NOT NULL,
    CONSTRAINT uq_asiento_localidad_fila_numero UNIQUE (id_localidad, fila, numero),
    CONSTRAINT ck_asiento_numero CHECK (numero > 0),
    INDEX ix_asiento_id_localidad (id_localidad)
) ENGINE=InnoDB;
