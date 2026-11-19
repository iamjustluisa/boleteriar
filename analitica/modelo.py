"""Modelo dimensional (esquema en estrella) del Data Warehouse · esquema_analitica.

Dimensiones: tiempo, evento, localidad y usuario. Hechos: venta (una fila por boleta), reserva
(una fila por reserva), ocupación (foto por evento y localidad) y crédito (un movimiento por fila).
Las llaves sk_* son sustitutas (propias del DW); id_* conservan la llave natural del origen.
"""
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DimTiempo(Base):
    __tablename__ = "dim_tiempo"
    sk_tiempo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # AAAAMMDD
    fecha: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    trimestre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    nombre_mes: Mapped[str] = mapped_column(String(12), nullable=False)
    dia: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dia_semana: Mapped[str] = mapped_column(String(10), nullable=False)
    fin_de_semana: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class DimEvento(Base):
    __tablename__ = "dim_evento"
    sk_evento: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_evento: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[time] = mapped_column(Time, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    id_escenario: Mapped[int] = mapped_column(Integer, nullable=False)
    escenario: Mapped[str] = mapped_column(String(100), nullable=False)
    capacidad_escenario: Mapped[int] = mapped_column(Integer, nullable=False)


class DimLocalidad(Base):
    __tablename__ = "dim_localidad"
    sk_localidad: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_localidad: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    escenario: Mapped[str] = mapped_column(String(100), nullable=False)
    precio_actual: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    capacidad: Mapped[int] = mapped_column(Integer, nullable=False)


class DimUsuario(Base):
    """Sin datos personales: solo el identificador y el rol (minimización de datos)."""
    __tablename__ = "dim_usuario"
    sk_usuario: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    rol: Mapped[str] = mapped_column(String(30), nullable=False)


class FactVenta(Base):
    """Grano: una boleta emitida."""
    __tablename__ = "fact_venta"
    id_boleta: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    sk_tiempo: Mapped[int] = mapped_column(ForeignKey("dim_tiempo.sk_tiempo"), nullable=False, index=True)
    sk_evento: Mapped[int] = mapped_column(ForeignKey("dim_evento.sk_evento"), nullable=False, index=True)
    sk_localidad: Mapped[int] = mapped_column(ForeignKey("dim_localidad.sk_localidad"), nullable=False, index=True)
    sk_usuario: Mapped[int] = mapped_column(ForeignKey("dim_usuario.sk_usuario"), nullable=False, index=True)
    id_compra: Mapped[int] = mapped_column(Integer, nullable=False)
    precio: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    estado_boleta: Mapped[str] = mapped_column(String(10), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(10), nullable=False)


class FactReserva(Base):
    """Grano: una reserva."""
    __tablename__ = "fact_reserva"
    id_reserva: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    sk_tiempo: Mapped[int] = mapped_column(ForeignKey("dim_tiempo.sk_tiempo"), nullable=False, index=True)
    sk_evento: Mapped[int] = mapped_column(ForeignKey("dim_evento.sk_evento"), nullable=False, index=True)
    sk_usuario: Mapped[int] = mapped_column(ForeignKey("dim_usuario.sk_usuario"), nullable=False, index=True)
    asientos: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    pagada: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class FactOcupacion(Base):
    """Grano: foto del estado de los asientos por evento y localidad en el momento de la carga."""
    __tablename__ = "fact_ocupacion"
    sk_evento: Mapped[int] = mapped_column(ForeignKey("dim_evento.sk_evento"), primary_key=True)
    sk_localidad: Mapped[int] = mapped_column(ForeignKey("dim_localidad.sk_localidad"), primary_key=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    disponibles: Mapped[int] = mapped_column(Integer, nullable=False)
    reservados: Mapped[int] = mapped_column(Integer, nullable=False)
    vendidos: Mapped[int] = mapped_column(Integer, nullable=False)


class FactCredito(Base):
    """Grano: un movimiento de créditos (abono o uso)."""
    __tablename__ = "fact_credito"
    id_credito: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    sk_tiempo: Mapped[int] = mapped_column(ForeignKey("dim_tiempo.sk_tiempo"), nullable=False, index=True)
    sk_usuario: Mapped[int] = mapped_column(ForeignKey("dim_usuario.sk_usuario"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(6), nullable=False)
    concepto: Mapped[str] = mapped_column(String(20), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)


class EtlEjecucion(Base):
    """Bitácora de cada ejecución del ETL."""
    __tablename__ = "etl_ejecucion"
    id_ejecucion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(String(10), nullable=False)  # ok | error
    origen: Mapped[str] = mapped_column(String(20), nullable=False)  # manual | programado
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
