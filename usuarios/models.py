"""Esquema esquema_usuarios (Tabla 48 del modelo relacional)."""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    correo: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    telefono: Mapped[str] = mapped_column(String(20), nullable=False)
    documento: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
