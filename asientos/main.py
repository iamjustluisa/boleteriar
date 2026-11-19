"""Microservicio de Asientos · esquema_asientos (Tabla 53) · RF-ASI-01 y 02."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app
from common.auth import requiere
from common.clients import disponibilidad, localidades, parse_ids
from common.errors import ErrorServicio, ServicioNoDisponible
from common.security import exigir_clave_interna

from .database import Base, engine, get_db, preparar


class Asiento(Base):
    __tablename__ = "asiento"
    __table_args__ = (
        UniqueConstraint("id_localidad", "fila", "numero", name="uq_asiento_localidad_fila_numero"),
        CheckConstraint("numero > 0", name="ck_asiento_numero"),
    )
    id_asiento: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_localidad: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Localidades
    fila: Mapped[str] = mapped_column(String(5), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)


Fila = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1,
                                        max_length=5, pattern=r"^[A-Z0-9]+$")]


class AsientoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_localidad: int
    fila: Fila
    numero: int = Field(gt=0)


class GenerarIn(BaseModel):
    """Crea una cuadrícula de asientos: filas A, B, C... con números 1..asientos_por_fila."""
    model_config = ConfigDict(extra="forbid")
    id_localidad: int
    filas: int = Field(gt=0, le=26)
    asientos_por_fila: int = Field(gt=0, le=60)
    fila_inicial: Fila = "A"


class AsientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_asiento: int
    id_localidad: int
    fila: str
    numero: int


router = APIRouter()


def _contar(db: Session, id_localidad: int) -> int:
    return db.scalar(select(func.count()).select_from(Asiento).where(Asiento.id_localidad == id_localidad))


def _sincronizar(id_escenario: int) -> int:
    """Los asientos nuevos se publican en la disponibilidad de los eventos ya programados."""
    try:
        return disponibilidad.post("/internal/disponibilidad/sincronizar",
                                   {"id_escenario": id_escenario})["publicados"]
    except (ErrorServicio, ServicioNoDisponible):
        return 0


def _filas_desde(inicial: str, n: int) -> list[str]:
    if inicial.isdigit():
        return [str(int(inicial) + i) for i in range(n)]
    base = ord(inicial[0])
    if base + n - 1 > ord("Z"):
        raise HTTPException(422, "Las filas pasan de la Z; usa una fila inicial anterior")
    return [chr(base + i) for i in range(n)]


@router.get("/asientos", response_model=list[AsientoOut], tags=["Asientos"],
            summary="RF-ASI-02 Consultar asientos de una localidad")
def listar(id_localidad: int, _: dict = Depends(requiere("consultar_eventos")),
           db: Session = Depends(get_db)):
    return db.scalars(select(Asiento).where(Asiento.id_localidad == id_localidad)
                      .order_by(Asiento.fila, Asiento.numero)).all()


@router.post("/asientos", response_model=AsientoOut, status_code=201, tags=["Asientos"],
             summary="RF-ASI-01 Registrar un asiento")
def crear(datos: AsientoIn, actor: dict = Depends(requiere("gestionar_asientos")),
          db: Session = Depends(get_db)):
    loc = localidades.get(f"/internal/localidades/{datos.id_localidad}")
    if _contar(db, datos.id_localidad) >= loc["capacidad"]:
        raise HTTPException(409, f"La localidad «{loc['nombre']}» ya está completa ({loc['capacidad']} asientos)")
    a = Asiento(**datos.model_dump())
    db.add(a)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"El asiento {datos.fila}-{datos.numero} ya existe en esta localidad")
    _sincronizar(loc["id_escenario"])
    auditoria.registrar("CREAR_ASIENTO", "ASIENTO", a.id_asiento, actor["id_usuario"], f"{a.fila}-{a.numero}")
    return a


@router.post("/asientos/generar", tags=["Asientos"],
             summary="RF-ASI-01 Generar varios asientos (filas × asientos por fila)")
def generar(datos: GenerarIn, actor: dict = Depends(requiere("gestionar_asientos")),
            db: Session = Depends(get_db)):
    loc = localidades.get(f"/internal/localidades/{datos.id_localidad}")
    existentes = {(a.fila, a.numero) for a in db.scalars(
        select(Asiento).where(Asiento.id_localidad == datos.id_localidad))}
    nuevos = [(f, n) for f in _filas_desde(datos.fila_inicial, datos.filas)
              for n in range(1, datos.asientos_por_fila + 1) if (f, n) not in existentes]
    if len(existentes) + len(nuevos) > loc["capacidad"]:
        raise HTTPException(409, f"Se superaría la capacidad de «{loc['nombre']}»: tiene "
                                 f"{len(existentes)} de {loc['capacidad']} asientos y se intentan crear {len(nuevos)}")
    db.add_all(Asiento(id_localidad=datos.id_localidad, fila=f, numero=n) for f, n in nuevos)
    db.commit()
    publicados = _sincronizar(loc["id_escenario"]) if nuevos else 0
    auditoria.registrar("GENERAR_ASIENTOS", "LOCALIDAD", datos.id_localidad, actor["id_usuario"],
                        f"{len(nuevos)} asientos")
    return {"creados": len(nuevos), "total_localidad": len(existentes) + len(nuevos),
            "publicados_en_eventos": publicados}


# ---------------- Internas ----------------
@router.get("/internal/asientos", response_model=list[AsientoOut], include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_varios(ids: str = "", localidades: str = "", db: Session = Depends(get_db)):
    if not ids and not localidades:
        return []
    q = select(Asiento)
    if ids:
        q = q.where(Asiento.id_asiento.in_(parse_ids(ids)))
    if localidades:
        q = q.where(Asiento.id_localidad.in_(parse_ids(localidades)))
    return db.scalars(q.order_by(Asiento.id_localidad, Asiento.fila, Asiento.numero)).all()


@router.get("/internal/asientos/contar", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_contar(id_localidad: int, db: Session = Depends(get_db)):
    return {"total": _contar(db, id_localidad)}


app = crear_app("asientos", "Microservicio de Asientos",
                "Administrar los asientos que componen cada localidad (RF-ASI-01 y 02).",
                router, Base, engine, preparar)
