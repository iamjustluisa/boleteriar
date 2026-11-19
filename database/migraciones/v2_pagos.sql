-- Parte de la migración v2 que solo se aplica una vez: método de pago y valor pagado con créditos.
ALTER TABLE esquema_pagos.pago
  ADD COLUMN metodo ENUM('tarjeta','creditos','mixto') NOT NULL DEFAULT 'tarjeta',
  ADD COLUMN valor_creditos DECIMAL(12,2) NOT NULL DEFAULT 0,
  ADD CONSTRAINT ck_pago_valor_creditos CHECK (valor_creditos >= 0);
