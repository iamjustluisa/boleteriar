-- Microservicio de Control de Acceso · Tabla 49
USE esquema_acceso;

CREATE TABLE IF NOT EXISTS rol (
    id_rol      INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(30)  NOT NULL,
    descripcion VARCHAR(150),
    CONSTRAINT uq_rol_nombre UNIQUE (nombre)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS permiso (
    id_permiso  INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(60)  NOT NULL,
    descripcion VARCHAR(150),
    CONSTRAINT uq_permiso_nombre UNIQUE (nombre)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rol_permiso (
    id_rol     INT NOT NULL,
    id_permiso INT NOT NULL,
    PRIMARY KEY (id_rol, id_permiso),
    CONSTRAINT fk_rp_rol     FOREIGN KEY (id_rol)     REFERENCES rol(id_rol)         ON DELETE RESTRICT,
    CONSTRAINT fk_rp_permiso FOREIGN KEY (id_permiso) REFERENCES permiso(id_permiso) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- id_usuario es referencia lógica a esquema_usuarios.usuario (otro microservicio): sin FK física.
CREATE TABLE IF NOT EXISTS credencial (
    id_credencial   INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario      INT NOT NULL,
    id_rol          INT NOT NULL,
    contrasena_hash VARCHAR(255) NOT NULL,
    estado          ENUM('activa','bloqueada') NOT NULL DEFAULT 'activa',
    CONSTRAINT uq_credencial_usuario UNIQUE (id_usuario),
    CONSTRAINT fk_credencial_rol FOREIGN KEY (id_rol) REFERENCES rol(id_rol) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- token guarda el SHA-256 (hex, 64 caracteres) del token entregado al cliente.
CREATE TABLE IF NOT EXISTS sesion (
    id_sesion     INT AUTO_INCREMENT PRIMARY KEY,
    id_credencial INT NOT NULL,
    token         VARCHAR(255) NOT NULL,
    fecha_inicio  DATETIME NOT NULL,
    fecha_fin     DATETIME NULL,
    estado        ENUM('activa','cerrada','expirada') NOT NULL DEFAULT 'activa',
    CONSTRAINT uq_sesion_token UNIQUE (token),
    CONSTRAINT fk_sesion_credencial FOREIGN KEY (id_credencial)
        REFERENCES credencial(id_credencial) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Roles y permisos base (el servicio también los siembra al iniciar; es idempotente)
INSERT IGNORE INTO rol (nombre, descripcion) VALUES
    ('usuario', 'Comprador de boletas'),
    ('administrador', 'Administra escenarios, eventos, roles y auditoría');

INSERT IGNORE INTO permiso (nombre, descripcion) VALUES
    ('consultar_eventos', 'Consultar eventos y su disponibilidad'),
    ('reservar_asientos', 'Reservar asientos de un evento'),
    ('comprar_boletas', 'Comprar los asientos de una reserva'),
    ('consultar_historial_propio', 'Ver reservas, compras y boletas propias'),
    ('gestionar_escenarios', 'Crear, editar y consultar escenarios'),
    ('gestionar_eventos', 'Crear, editar y cancelar eventos'),
    ('gestionar_localidades', 'Administrar localidades de un escenario'),
    ('gestionar_asientos', 'Administrar asientos de una localidad'),
    ('gestionar_roles', 'Asignar roles y permisos'),
    ('listar_usuarios', 'Listar usuarios registrados'),
    ('consultar_auditoria', 'Consultar la auditoría con filtros'),
    ('consultar_indicadores', 'Consultar indicadores y ejecutar el ETL del Data Warehouse');

INSERT IGNORE INTO rol_permiso (id_rol, id_permiso)
    SELECT r.id_rol, p.id_permiso FROM rol r JOIN permiso p WHERE r.nombre = 'administrador';

INSERT IGNORE INTO rol_permiso (id_rol, id_permiso)
    SELECT r.id_rol, p.id_permiso FROM rol r JOIN permiso p
    WHERE r.nombre = 'usuario'
      AND p.nombre IN ('consultar_eventos','reservar_asientos','comprar_boletas','consultar_historial_propio');
