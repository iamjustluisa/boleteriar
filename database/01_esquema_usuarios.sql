-- Microservicio de Usuarios · Tabla 48
USE esquema_usuarios;

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(80)  NOT NULL,
    apellido   VARCHAR(80)  NOT NULL,
    correo     VARCHAR(120) NOT NULL,
    telefono   VARCHAR(20)  NOT NULL,
    documento  VARCHAR(20)  NOT NULL,
    CONSTRAINT uq_usuario_correo    UNIQUE (correo),
    CONSTRAINT uq_usuario_documento UNIQUE (documento)
) ENGINE=InnoDB;
