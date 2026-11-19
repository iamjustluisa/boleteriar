-- Microservicio de Notificaciones · Tabla 59
USE esquema_notificaciones;

CREATE TABLE IF NOT EXISTS notificacion (
    id_notificacion INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario      INT          NOT NULL,            -- RL -> Usuarios
    tipo            ENUM('reserva','pago','expiracion','evento','credito') NOT NULL,
    id_referencia   INT          NOT NULL,
    mensaje         VARCHAR(255) NOT NULL,
    fecha_envio     DATETIME     NULL,
    estado          ENUM('pendiente','enviada') NOT NULL DEFAULT 'pendiente',
    INDEX ix_notificacion_id_usuario (id_usuario)
) ENGINE=InnoDB;
