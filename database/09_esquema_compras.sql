-- Microservicio de Compras · Tabla 56
USE esquema_compras;

CREATE TABLE IF NOT EXISTS compra (
    id_compra    INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario   INT           NOT NULL,              -- RL -> Usuarios
    id_reserva   INT           NOT NULL,              -- RL -> Reservas (una compra por reserva)
    fecha_compra DATETIME      NOT NULL,
    valor_total  DECIMAL(12,2) NOT NULL,
    estado       ENUM('pendiente','pagada','rechazada') NOT NULL DEFAULT 'pendiente',
    CONSTRAINT uq_compra_reserva UNIQUE (id_reserva),
    CONSTRAINT ck_compra_valor_total CHECK (valor_total >= 0),
    INDEX ix_compra_id_usuario (id_usuario)
) ENGINE=InnoDB;
