-- Microservicio de Disponibilidad · Tabla 54
-- La llave (id_evento, id_asiento) garantiza un único estado por asiento y evento (RN22).
-- El cambio de estado se hace con UPDATE ... WHERE estado = <esperado>, que bloquea la fila (RN15).
USE esquema_disponibilidad;

CREATE TABLE IF NOT EXISTS disponibilidad_asiento (
    id_evento  INT NOT NULL,                          -- RL -> Eventos
    id_asiento INT NOT NULL,                          -- RL -> Asientos
    estado     ENUM('disponible','reservado','vendido') NOT NULL DEFAULT 'disponible',
    PRIMARY KEY (id_evento, id_asiento),
    INDEX ix_disp_evento_estado (id_evento, estado)   -- RNF03: consultas de disponibilidad
) ENGINE=InnoDB;
