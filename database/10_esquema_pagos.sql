-- Microservicio de Pagos · Tabla 57 (pago simulado) + CREDITO (monedero del usuario)
USE esquema_pagos;

CREATE TABLE IF NOT EXISTS pago (
    id_pago        INT AUTO_INCREMENT PRIMARY KEY,
    id_compra      INT           NOT NULL,             -- RL -> Compras
    valor          DECIMAL(12,2) NOT NULL,
    fecha_pago     DATETIME      NOT NULL,
    estado         ENUM('aprobado','rechazado') NOT NULL,
    referencia     VARCHAR(60)   NOT NULL,
    metodo         ENUM('tarjeta','creditos','mixto') NOT NULL DEFAULT 'tarjeta',
    valor_creditos DECIMAL(12,2) NOT NULL DEFAULT 0,  -- parte del valor pagada con créditos
    CONSTRAINT uq_pago_referencia UNIQUE (referencia),
    CONSTRAINT ck_pago_valor CHECK (valor >= 0),
    CONSTRAINT ck_pago_valor_creditos CHECK (valor_creditos >= 0),
    INDEX ix_pago_id_compra (id_compra)
) ENGINE=InnoDB;

-- Movimientos de créditos. Saldo = Σ abonos − Σ usos.
--   abono · evento_cancelado : valor de la boleta de un evento cancelado (id_referencia = boleta)
--   abono · precio_justo     : diferencia cuando baja el precio de la localidad (id_referencia = boleta)
--   uso   · pago_compra      : créditos usados para pagar (id_referencia = compra)
CREATE TABLE IF NOT EXISTS credito (
    id_credito    INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario    INT           NOT NULL,              -- RL -> Usuarios
    tipo          ENUM('abono','uso') NOT NULL,
    concepto      ENUM('evento_cancelado','precio_justo','pago_compra') NOT NULL,
    monto         DECIMAL(12,2) NOT NULL,
    id_referencia INT           NOT NULL,
    descripcion   VARCHAR(255)  NOT NULL,
    fecha         DATETIME      NOT NULL,
    CONSTRAINT ck_credito_monto CHECK (monto > 0),
    INDEX ix_credito_id_usuario (id_usuario),
    INDEX ix_credito_id_referencia (id_referencia)
) ENGINE=InnoDB;
