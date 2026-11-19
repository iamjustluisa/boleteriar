-- Parte de la migración v2 que solo se aplica una vez (la ejecuta scripts/migrar.sh si hace falta):
-- unicidad de boletas vigentes por asiento y evento.
ALTER TABLE esquema_boletas.boleta
  ADD COLUMN vigente_unica TINYINT GENERATED ALWAYS AS (CASE WHEN estado = 'vigente' THEN 1 ELSE NULL END) STORED,
  DROP INDEX uq_boleta_evento_asiento,
  ADD CONSTRAINT uq_boleta_vigente_evento_asiento UNIQUE (id_evento, id_asiento, vigente_unica);
