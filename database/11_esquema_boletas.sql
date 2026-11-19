-- Microservicio de Boletas · Tabla 58
-- RF-BOL-03 / RN15: no puede haber más de una boleta VIGENTE por asiento y evento.
-- vigente_unica vale 1 solo si la boleta está vigente (NULL si está usada o cancelada); como UNIQUE
-- admite varios NULL, un asiento de un evento cancelado y reactivado puede venderse de nuevo.
USE esquema_boletas;

CREATE TABLE IF NOT EXISTS boleta (
    id_boleta     INT AUTO_INCREMENT PRIMARY KEY,
    id_compra     INT           NOT NULL,             -- RL -> Compras
    id_evento     INT           NOT NULL,             -- RL -> Eventos
    id_asiento    INT           NOT NULL,             -- RL -> Asientos
    codigo_boleta VARCHAR(40)   NOT NULL,
    precio        DECIMAL(10,2) NOT NULL,
    estado        ENUM('vigente','usada','cancelada') NOT NULL DEFAULT 'vigente',
    vigente_unica TINYINT GENERATED ALWAYS AS (CASE WHEN estado = 'vigente' THEN 1 ELSE NULL END) STORED,
    CONSTRAINT uq_boleta_codigo UNIQUE (codigo_boleta),
    CONSTRAINT uq_boleta_vigente_evento_asiento UNIQUE (id_evento, id_asiento, vigente_unica),
    CONSTRAINT ck_boleta_precio CHECK (precio >= 0),
    INDEX ix_boleta_id_compra (id_compra)
) ENGINE=InnoDB;
