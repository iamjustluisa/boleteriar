-- Microservicio de Reservas · Tabla 55
USE esquema_reservas;

CREATE TABLE IF NOT EXISTS reserva (
    id_reserva        INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario        INT      NOT NULL,              -- RL -> Usuarios
    id_evento         INT      NOT NULL,              -- RL -> Eventos
    fecha_reserva     DATETIME NOT NULL,
    fecha_vencimiento DATETIME NOT NULL,              -- RN16: vigencia configurable
    estado            ENUM('activa','cancelada','expirada','completada') NOT NULL DEFAULT 'activa',
    INDEX ix_reserva_id_usuario (id_usuario),
    INDEX ix_reserva_id_evento (id_evento),
    INDEX ix_reserva_estado_vencimiento (estado, fecha_vencimiento)
) ENGINE=InnoDB;

-- Entidad asociativa RESERVA–ASIENTO (M:N). RN14: ON DELETE RESTRICT, no hay borrado físico.
CREATE TABLE IF NOT EXISTS detalle_reserva (
    id_reserva INT NOT NULL,
    id_asiento INT NOT NULL,                          -- RL -> Asientos
    PRIMARY KEY (id_reserva, id_asiento),
    INDEX ix_detalle_reserva_id_asiento (id_asiento),
    CONSTRAINT fk_detalle_reserva FOREIGN KEY (id_reserva)
        REFERENCES reserva (id_reserva) ON DELETE RESTRICT
) ENGINE=InnoDB;
