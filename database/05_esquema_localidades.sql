-- Microservicio de Localidades · Tabla 52
USE esquema_localidades;

CREATE TABLE IF NOT EXISTS localidad (
    id_localidad INT AUTO_INCREMENT PRIMARY KEY,
    id_escenario INT           NOT NULL,              -- RL -> Escenarios
    nombre       VARCHAR(60)   NOT NULL,
    precio       DECIMAL(10,2) NOT NULL,
    capacidad    INT           NOT NULL,
    CONSTRAINT uq_localidad_escenario_nombre UNIQUE (id_escenario, nombre),
    CONSTRAINT ck_localidad_precio    CHECK (precio >= 0),
    CONSTRAINT ck_localidad_capacidad CHECK (capacidad > 0),
    INDEX ix_localidad_id_escenario (id_escenario)
) ENGINE=InnoDB;
