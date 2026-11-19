"""Esquema esquema_acceso (Tabla 49 del modelo relacional)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Entidad asociativa ROL_PERMISO (M:N)
rol_permiso = Table(
    "rol_permiso", Base.metadata,
    Column("id_rol", Integer, ForeignKey("rol.id_rol", ondelete="RESTRICT"), primary_key=True),
    Column("id_permiso", Integer, ForeignKey("permiso.id_permiso", ondelete="RESTRICT"), primary_key=True),
)


class Rol(Base):
    __tablename__ = "rol"
    id_rol: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(150))
    permisos: Mapped[list["Permiso"]] = relationship(secondary=rol_permiso, lazy="selectin")


class Permiso(Base):
    __tablename__ = "permiso"
    id_permiso: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(150))


class Credencial(Base):
    __tablename__ = "credencial"
    id_credencial: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Referencia lógica a esquema_usuarios.usuario (otro microservicio): sin FK física.
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol", ondelete="RESTRICT"), nullable=False)
    contrasena_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(Enum("activa", "bloqueada", name="estado_credencial"),
                                        nullable=False, default="activa")
    rol: Mapped[Rol] = relationship(lazy="joined")


class Sesion(Base):
    __tablename__ = "sesion"
    id_sesion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_credencial: Mapped[int] = mapped_column(
        ForeignKey("credencial.id_credencial", ondelete="RESTRICT"), nullable=False)
    # Se guarda el SHA-256 del token, no el token: una fuga de la tabla no entrega sesiones.
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(Enum("activa", "cerrada", "expirada", name="estado_sesion"),
                                        nullable=False, default="activa")
    credencial: Mapped[Credencial] = relationship(lazy="joined")
