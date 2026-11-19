"""Microservicio de Escenarios · esquema_escenarios (Tabla 50) · RF-ESC-01 a 03."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import CheckConstraint, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app
from common.auth import requiere
from common.clients import eventos, localidades, parse_ids
from common.security import exigir_clave_interna

from .database import Base, engine, get_db, preparar


# ---------------- Modelo ----------------
class Escenario(Base):
    __tablename__ = "escenario"
    __table_args__ = (CheckConstraint("capacidad > 0", name="ck_escenario_capacidad"),)

    id_escenario: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    direccion: Mapped[str] = mapped_column(String(150), nullable=False)
    capacidad: Mapped[int] = mapped_column(Integer, nullable=False)


# ---------------- Esquemas ----------------
Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Texto150 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class EscenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: Texto100
    direccion: Texto150
    capacidad: int = Field(gt=0, description="Capacidad total, mayor que cero")


class EscenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_escenario: int
    nombre: str
    direccion: str
    capacidad: int


router = APIRouter()


def _obtener(db: Session, id_escenario: int) -> Escenario:
    e = db.get(Escenario, id_escenario)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El escenario no existe")
    return e


# ---------------- Rutas públicas (con sesión) ----------------
@router.get("/escenarios", response_model=list[EscenarioOut], tags=["Escenarios"],
            summary="RF-ESC-02 Consultar escenarios")
def listar(_: dict = Depends(requiere("consultar_eventos")), db: Session = Depends(get_db)):
    return db.scalars(select(Escenario).order_by(Escenario.nombre)).all()


@router.get("/escenarios/{id_escenario}", response_model=EscenarioOut, tags=["Escenarios"])
def detalle(id_escenario: int, _: dict = Depends(requiere("consultar_eventos")),
            db: Session = Depends(get_db)):
    return _obtener(db, id_escenario)


# ---------------- Administración ----------------
@router.post("/escenarios", response_model=EscenarioOut, status_code=201, tags=["Escenarios"],
             summary="RF-ESC-01 Registrar escenario")
def crear(datos: EscenarioIn, actor: dict = Depends(requiere("gestionar_escenarios")),
          db: Session = Depends(get_db)):
    e = Escenario(**datos.model_dump())
    db.add(e)
    db.commit()
    auditoria.registrar("CREAR_ESCENARIO", "ESCENARIO", e.id_escenario, actor["id_usuario"], e.nombre)
    return e


@router.put("/escenarios/{id_escenario}", response_model=EscenarioOut, tags=["Escenarios"],
            summary="RF-ESC-02 Actualizar escenario")
def actualizar(id_escenario: int, datos: EscenarioIn,
               actor: dict = Depends(requiere("gestionar_escenarios")), db: Session = Depends(get_db)):
    e = _obtener(db, id_escenario)
    if datos.capacidad < e.capacidad:
        ocupada = localidades.get("/internal/localidades/capacidad", id_escenario=id_escenario)["total"]
        if datos.capacidad < ocupada:
            raise HTTPException(409, f"La capacidad no puede ser menor que la suma de sus localidades ({ocupada})")
    for k, v in datos.model_dump().items():
        setattr(e, k, v)
    db.commit()
    auditoria.registrar("ACTUALIZAR_ESCENARIO", "ESCENARIO", e.id_escenario, actor["id_usuario"])
    return e


@router.delete("/escenarios/{id_escenario}", status_code=204, tags=["Escenarios"],
               summary="RF-ESC-03 Eliminar escenario (solo si no tiene eventos ni localidades)")
def eliminar(id_escenario: int, actor: dict = Depends(requiere("gestionar_escenarios")),
             db: Session = Depends(get_db)):
    e = _obtener(db, id_escenario)
    n_eventos = eventos.get("/internal/eventos/contar", id_escenario=id_escenario)["total"]
    n_loc = localidades.get("/internal/localidades/contar", id_escenario=id_escenario)["total"]
    if n_eventos or n_loc:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"No se puede eliminar «{e.nombre}»: tiene {n_eventos} evento(s) y "
                            f"{n_loc} localidad(es) asociadas")
    db.delete(e)
    db.commit()
    auditoria.registrar("ELIMINAR_ESCENARIO", "ESCENARIO", id_escenario, actor["id_usuario"], e.nombre)


# ---------------- Internas ----------------
@router.get("/internal/escenarios", response_model=list[EscenarioOut], include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_varios(ids: str = "", db: Session = Depends(get_db)):
    lista = parse_ids(ids)
    q = select(Escenario)
    if lista:
        q = q.where(Escenario.id_escenario.in_(lista))
    return db.scalars(q).all()


@router.get("/internal/escenarios/{id_escenario}", response_model=EscenarioOut,
            include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_uno(id_escenario: int, db: Session = Depends(get_db)):
    return _obtener(db, id_escenario)


app = crear_app("escenarios", "Microservicio de Escenarios",
                "Administrar los escenarios donde se realizan los eventos (RF-ESC-01 a 03).",
                router, Base, engine, preparar)
