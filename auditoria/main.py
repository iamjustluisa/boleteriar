"""Microservicio de Auditoría · esquema_auditoria (Tabla 60) · RF-AUD-01 a 03, RN19, RN20.

Solo existe la operación de insertar (interna) y la de consultar con filtros (administrador).
Ningún endpoint permite editar o borrar registros; además, en MySQL hay triggers que rechazan
UPDATE y DELETE sobre la tabla (ver database/13_esquema_auditoria.sql).
"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from common.app import crear_app
from common.auth import requiere
from common.clients import ids_param, usuarios
from common.errors import ServicioNoDisponible
from common.security import exigir_clave_interna, utcnow

from .database import Base, engine, get_db, preparar


class Auditoria(Base):
    __tablename__ = "auditoria"
    id_auditoria: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # RL -> Usuarios
    accion: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column(String(60), nullable=False)
    id_entidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    detalle: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuditoriaIn(BaseModel):
    id_usuario: int | None = None
    accion: str = Field(min_length=1, max_length=60)
    entidad: str = Field(min_length=1, max_length=60)
    id_entidad: int | None = None
    fecha_hora: datetime | None = None
    detalle: str | None = Field(default=None, max_length=255)


router = APIRouter()


@router.get("/auditoria", tags=["Auditoría"],
            summary="RF-AUD-03 Consultar la auditoría filtrando por usuario, acción y fecha")
def consultar(id_usuario: int | None = None, accion: str | None = None, desde: date | None = None,
              hasta: date | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
              _: dict = Depends(requiere("consultar_auditoria")), db: Session = Depends(get_db)):
    filtros = []
    if id_usuario:
        filtros.append(Auditoria.id_usuario == id_usuario)
    if accion:
        filtros.append(Auditoria.accion == accion)
    if desde:
        filtros.append(Auditoria.fecha_hora >= datetime.combine(desde, time.min))
    if hasta:
        filtros.append(Auditoria.fecha_hora < datetime.combine(hasta + timedelta(days=1), time.min))
    total = db.scalar(select(func.count()).select_from(Auditoria).where(*filtros))
    filas = db.scalars(select(Auditoria).where(*filtros).order_by(Auditoria.id_auditoria.desc())
                       .limit(limit).offset(offset)).all()
    nombres = {}
    ids_u = {f.id_usuario for f in filas if f.id_usuario}
    if ids_u:
        try:
            nombres = {u["id_usuario"]: f"{u['nombre']} {u['apellido']}"
                       for u in usuarios.get("/internal/usuarios", ids=ids_param(ids_u))}
        except ServicioNoDisponible:
            pass
    return {"total": total, "items": [{
        "id_auditoria": f.id_auditoria, "id_usuario": f.id_usuario, "usuario": nombres.get(f.id_usuario),
        "accion": f.accion, "entidad": f.entidad, "id_entidad": f.id_entidad,
        "fecha_hora": f.fecha_hora, "detalle": f.detalle} for f in filas]}


@router.get("/auditoria/acciones", tags=["Auditoría"], summary="Acciones registradas (para filtrar)")
def acciones(_: dict = Depends(requiere("consultar_auditoria")), db: Session = Depends(get_db)):
    return sorted(db.scalars(select(Auditoria.accion).distinct()).all())


@router.post("/internal/auditoria", status_code=201, include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_registrar(datos: AuditoriaIn, db: Session = Depends(get_db)):
    """RF-AUD-01. Única forma de escribir en la tabla: solo INSERT."""
    a = Auditoria(**{**datos.model_dump(), "fecha_hora": datos.fecha_hora or utcnow()})
    db.add(a)
    db.commit()
    return {"id_auditoria": a.id_auditoria}


_PG_INMUTABLE = """
CREATE OR REPLACE FUNCTION auditoria_inmutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'RN19: los registros de auditoria no se pueden modificar ni eliminar';
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria;
CREATE TRIGGER trg_auditoria_inmutable BEFORE UPDATE OR DELETE ON auditoria
  FOR EACH ROW EXECUTE FUNCTION auditoria_inmutable();
"""


def _proteger() -> None:
    """RN19 en PostgreSQL (Neon). En MySQL lo hacen los triggers de database/13_esquema_auditoria.sql."""
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text
        with engine.begin() as c:
            c.execute(text(_PG_INMUTABLE))


app = crear_app("auditoria", "Microservicio de Auditoría",
                "Registro inmutable de operaciones críticas y su consulta (RF-AUD-01 a 03).",
                router, Base, engine, preparar, al_iniciar=_proteger)
