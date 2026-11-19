-- Sprint 7 · Data Warehouse (esquema en estrella) del microservicio de Analítica.
-- Dimensiones: dim_tiempo, dim_evento, dim_localidad, dim_usuario.
-- Hechos: fact_venta (grano boleta), fact_reserva (grano reserva), fact_ocupacion (foto evento x localidad),
-- fact_credito (grano movimiento). El ETL (analitica/etl.py) la recarga por completo en cada ejecución.
USE esquema_analitica;

CREATE TABLE IF NOT EXISTS dim_evento (
	sk_evento INTEGER NOT NULL AUTO_INCREMENT, 
	id_evento INTEGER NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	fecha DATE NOT NULL, 
	hora TIME NOT NULL, 
	estado VARCHAR(12) NOT NULL, 
	id_escenario INTEGER NOT NULL, 
	escenario VARCHAR(100) NOT NULL, 
	capacidad_escenario INTEGER NOT NULL, 
	PRIMARY KEY (sk_evento), 
	UNIQUE (id_evento)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS dim_localidad (
	sk_localidad INTEGER NOT NULL AUTO_INCREMENT, 
	id_localidad INTEGER NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	escenario VARCHAR(100) NOT NULL, 
	precio_actual NUMERIC(10, 2) NOT NULL, 
	capacidad INTEGER NOT NULL, 
	PRIMARY KEY (sk_localidad), 
	UNIQUE (id_localidad)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS dim_tiempo (
	sk_tiempo INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	anio SMALLINT NOT NULL, 
	trimestre SMALLINT NOT NULL, 
	mes SMALLINT NOT NULL, 
	nombre_mes VARCHAR(12) NOT NULL, 
	dia SMALLINT NOT NULL, 
	dia_semana VARCHAR(10) NOT NULL, 
	fin_de_semana SMALLINT NOT NULL, 
	PRIMARY KEY (sk_tiempo), 
	UNIQUE (fecha)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS dim_usuario (
	sk_usuario INTEGER NOT NULL AUTO_INCREMENT, 
	id_usuario INTEGER NOT NULL, 
	rol VARCHAR(30) NOT NULL, 
	PRIMARY KEY (sk_usuario), 
	UNIQUE (id_usuario)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS etl_ejecucion (
	id_ejecucion INTEGER NOT NULL AUTO_INCREMENT, 
	inicio DATETIME NOT NULL, 
	fin DATETIME, 
	estado VARCHAR(10) NOT NULL, 
	origen VARCHAR(20) NOT NULL, 
	detalle TEXT, 
	PRIMARY KEY (id_ejecucion)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS fact_credito (
	id_credito INTEGER NOT NULL, 
	sk_tiempo INTEGER NOT NULL, 
	sk_usuario INTEGER NOT NULL, 
	tipo VARCHAR(6) NOT NULL, 
	concepto VARCHAR(20) NOT NULL, 
	monto NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (id_credito), 
	FOREIGN KEY(sk_tiempo) REFERENCES dim_tiempo (sk_tiempo), 
	FOREIGN KEY(sk_usuario) REFERENCES dim_usuario (sk_usuario)
) ENGINE=InnoDB;

CREATE INDEX ix_fact_credito_sk_tiempo ON fact_credito (sk_tiempo);
CREATE INDEX ix_fact_credito_sk_usuario ON fact_credito (sk_usuario);

CREATE TABLE IF NOT EXISTS fact_ocupacion (
	sk_evento INTEGER NOT NULL, 
	sk_localidad INTEGER NOT NULL, 
	total INTEGER NOT NULL, 
	disponibles INTEGER NOT NULL, 
	reservados INTEGER NOT NULL, 
	vendidos INTEGER NOT NULL, 
	PRIMARY KEY (sk_evento, sk_localidad), 
	FOREIGN KEY(sk_evento) REFERENCES dim_evento (sk_evento), 
	FOREIGN KEY(sk_localidad) REFERENCES dim_localidad (sk_localidad)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS fact_reserva (
	id_reserva INTEGER NOT NULL, 
	sk_tiempo INTEGER NOT NULL, 
	sk_evento INTEGER NOT NULL, 
	sk_usuario INTEGER NOT NULL, 
	asientos INTEGER NOT NULL, 
	estado VARCHAR(12) NOT NULL, 
	pagada SMALLINT NOT NULL, 
	PRIMARY KEY (id_reserva), 
	FOREIGN KEY(sk_tiempo) REFERENCES dim_tiempo (sk_tiempo), 
	FOREIGN KEY(sk_evento) REFERENCES dim_evento (sk_evento), 
	FOREIGN KEY(sk_usuario) REFERENCES dim_usuario (sk_usuario)
) ENGINE=InnoDB;

CREATE INDEX ix_fact_reserva_sk_tiempo ON fact_reserva (sk_tiempo);
CREATE INDEX ix_fact_reserva_sk_evento ON fact_reserva (sk_evento);
CREATE INDEX ix_fact_reserva_sk_usuario ON fact_reserva (sk_usuario);

CREATE TABLE IF NOT EXISTS fact_venta (
	id_boleta INTEGER NOT NULL, 
	sk_tiempo INTEGER NOT NULL, 
	sk_evento INTEGER NOT NULL, 
	sk_localidad INTEGER NOT NULL, 
	sk_usuario INTEGER NOT NULL, 
	id_compra INTEGER NOT NULL, 
	precio NUMERIC(10, 2) NOT NULL, 
	estado_boleta VARCHAR(10) NOT NULL, 
	metodo_pago VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id_boleta), 
	FOREIGN KEY(sk_tiempo) REFERENCES dim_tiempo (sk_tiempo), 
	FOREIGN KEY(sk_evento) REFERENCES dim_evento (sk_evento), 
	FOREIGN KEY(sk_localidad) REFERENCES dim_localidad (sk_localidad), 
	FOREIGN KEY(sk_usuario) REFERENCES dim_usuario (sk_usuario)
) ENGINE=InnoDB;

CREATE INDEX ix_fact_venta_sk_tiempo ON fact_venta (sk_tiempo);
CREATE INDEX ix_fact_venta_sk_evento ON fact_venta (sk_evento);
CREATE INDEX ix_fact_venta_sk_localidad ON fact_venta (sk_localidad);
CREATE INDEX ix_fact_venta_sk_usuario ON fact_venta (sk_usuario);
