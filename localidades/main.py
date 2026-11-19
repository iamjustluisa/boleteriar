"""Microservicio de Localidades · esquema_localidades (Tabla 52) · RF-LOC-01 y 02."""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import (CheckConstraint, Integer, Numeric, String, UniqueConstraint, func,
                        select)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app
from common.auth import requiere
from common.clients import asientos, boletas, escenarios, parse_ids
from common.errors import ErrorServicio, ServicioNoDisponible
from common.security import exigir_clave_interna

from .database import Base, engine, get_db, preparar


class Localidad(Base):
    __tablename__ = "localidad"
    __table_args__ = (
        UniqueConstraint("id_escenario", "nombre", name="uq_localidad_escenario_nombre"),
        CheckConstraint("precio >= 0", name="ck_localidad_precio"),
        CheckConstraint("capacidad > 0", name="ck_localidad_capacidad"),
    )
    id_localidad: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_escenario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Escenarios
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    capacidad: Mapped[int] = mapped_column(Integer, nullable=False)


Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class LocalidadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_escenario: int
    nombre: Nombre
    precio: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    capacidad: int = Field(gt=0)


class LocalidadUpd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: Nombre
    precio: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    capacidad: int = Field(gt=0)


class LocalidadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_localidad: int
    id_escenario: int
    nombre: str
    precio: float
    capacidad: int


router = APIRouter()


def _obtener(db: Session, id_localidad: int) -> Localidad:
    loc = db.get(Localidad, id_localidad)
    if loc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La localidad no existe")
    return loc


def _capacidad_usada(db: Session, id_escenario: int, excluir: int | None = None) -> int:
    q = select(func.coalesce(func.sum(Localidad.capacidad), 0)).where(Localidad.id_escenario == id_escenario)
    if excluir:
        q = q.where(Localidad.id_localidad != excluir)
    return int(db.scalar(q) or 0)


def _validar_capacidad(db: Session, id_escenario: int, nueva: int, excluir: int | None = None) -> None:
    esc = escenarios.get(f"/internal/escenarios/{id_escenario}")
    usada = _capacidad_usada(db, id_escenario, excluir)
    if usada + nueva > esc["capacidad"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"La capacidad supera la del escenario: quedan {esc['capacidad'] - usada} "
                            f"de {esc['capacidad']} lugares sin asignar a una localidad")


@router.get("/localidades", response_model=list[LocalidadOut], tags=["Localidades"],
            summary="RF-LOC-02 Consultar localidades de un escenario")
def listar(id_escenario: int | None = None, _: dict = Depends(requiere("consultar_eventos")),
           db: Session = Depends(get_db)):
    q = select(Localidad).order_by(Localidad.precio.desc(), Localidad.nombre)
    if id_escenario:
        q = q.where(Localidad.id_escenario == id_escenario)
    return db.scalars(q).all()


@router.post("/localidades", response_model=LocalidadOut, status_code=201, tags=["Localidades"],
             summary="RF-LOC-01 Registrar localidad")
def crear(datos: LocalidadIn, actor: dict = Depends(requiere("gestionar_localidades")),
          db: Session = Depends(get_db)):
    _validar_capacidad(db, datos.id_escenario, datos.capacidad)  # valida también que exista
    loc = Localidad(**datos.model_dump())
    db.add(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Ya existe una localidad llamada «{datos.nombre}» en este escenario")
    auditoria.registrar("CREAR_LOCALIDAD", "LOCALIDAD", loc.id_localidad, actor["id_usuario"],
                        f"{loc.nombre} ${loc.precio}")
    return loc


@router.put("/localidades/{id_localidad}", tags=["Localidades"],
            summary="RF-LOC-02 Actualizar localidad (no altera boletas emitidas; si baja el precio aplica Precio Justo)")
def actualizar(id_localidad: int, datos: LocalidadUpd,
               actor: dict = Depends(requiere("gestionar_localidades")), db: Session = Depends(get_db)):
    loc = _obtener(db, id_localidad)
    if datos.capacidad != loc.capacidad:
        _validar_capacidad(db, loc.id_escenario, datos.capacidad, excluir=loc.id_localidad)
        n = asientos.get("/internal/asientos/contar", id_localidad=id_localidad)["total"]
        if datos.capacidad < n:
            raise HTTPException(409, f"La localidad ya tiene {n} asientos registrados")
    anterior = loc.precio
    loc.nombre, loc.precio, loc.capacidad = datos.nombre, datos.precio, datos.capacidad
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Ya existe una localidad llamada «{datos.nombre}» en este escenario")
    auditoria.registrar("ACTUALIZAR_LOCALIDAD", "LOCALIDAD", loc.id_localidad, actor["id_usuario"],
                        f"precio {anterior} -> {loc.precio}")
    precio_justo = None
    if loc.precio < anterior:  # Precio Justo Garantizado: se devuelve la diferencia a quienes ya compraron
        try:
            precio_justo = boletas.post("/internal/boletas/precio-justo",
                                        {"id_localidad": loc.id_localidad, "precio_nuevo": float(loc.precio)})
            if precio_justo["total"]:
                auditoria.registrar("PRECIO_JUSTO", "LOCALIDAD", loc.id_localidad, actor["id_usuario"],
                                    f"{precio_justo['boletas']} boletas, {precio_justo['total']} en créditos")
        except (ErrorServicio, ServicioNoDisponible) as exc:
            precio_justo = {"error": str(exc)}
    return {**LocalidadOut.model_validate(loc).model_dump(), "precio_justo": precio_justo}


@router.delete("/localidades/{id_localidad}", status_code=204, tags=["Localidades"])
def eliminar(id_localidad: int, actor: dict = Depends(requiere("gestionar_localidades")),
             db: Session = Depends(get_db)):
    loc = _obtener(db, id_localidad)
    n = asientos.get("/internal/asientos/contar", id_localidad=id_localidad)["total"]
    if n:
        raise HTTPException(409, f"No se puede eliminar: la localidad tiene {n} asientos")
    db.delete(loc)
    db.commit()
    auditoria.registrar("ELIMINAR_LOCALIDAD", "LOCALIDAD", id_localidad, actor["id_usuario"], loc.nombre)


# ---------------- Internas ----------------
@router.get("/internal/localidades", response_model=list[LocalidadOut], include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_varios(ids: str = "", escenarios: str = "", db: Session = Depends(get_db)):
    q = select(Localidad)
    if ids:
        q = q.where(Localidad.id_localidad.in_(parse_ids(ids)))
    if escenarios:
        q = q.where(Localidad.id_escenario.in_(parse_ids(escenarios)))
    return db.scalars(q.order_by(Localidad.precio.desc())).all()


@router.get("/internal/localidades/contar", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_contar(id_escenario: int, db: Session = Depends(get_db)):
    return {"total": db.scalar(select(func.count()).select_from(Localidad)
                               .where(Localidad.id_escenario == id_escenario))}


@router.get("/internal/localidades/capacidad", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_capacidad(id_escenario: int, db: Session = Depends(get_db)):
    return {"total": _capacidad_usada(db, id_escenario)}


@router.get("/internal/localidades/{id_localidad}", response_model=LocalidadOut,
            include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_uno(id_localidad: int, db: Session = Depends(get_db)):
    return _obtener(db, id_localidad)


app = crear_app("localidades", "Microservicio de Localidades",
                "Administrar las zonas de cada escenario con su precio base (RF-LOC-01 y 02).",
                router, Base, engine, preparar)
