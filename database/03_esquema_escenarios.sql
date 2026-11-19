-- Microservicio de Escenarios · Tabla 50
USE esquema_escenarios;

CREATE TABLE IF NOT EXISTS escenario (
    id_escenario INT AUTO_INCREMENT PRIMARY KEY,
    nombre       VARCHAR(100) NOT NULL,
    direccion    VARCHAR(150) NOT NULL,
    capacidad    INT          NOT NULL,
    CONSTRAINT ck_escenario_capacidad CHECK (capacidad > 0)
) ENGINE=InnoDB;
