"""Microservicio de Notificaciones · esquema_notificaciones (Tabla 59) · RF-NOT-01 a 03, RN21.

Las notificaciones se registran como *pendiente* y pasan a *enviada* (con su fecha_envio) cuando
se entregan al usuario en la aplicación. No se envían correos reales (fuera del alcance).
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Enum, Integer, String, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from common.app import crear_app
from common.auth import sesion_actual
from common.security import exigir_clave_interna, utcnow

from .database import Base, engine, get_db, preparar


class Notificacion(Base):
    __tablename__ = "notificacion"
    id_notificacion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Usuarios
    tipo: Mapped[str] = mapped_column(Enum("reserva", "pago", "expiracion", "evento", "credito", name="tipo_notificacion"),
                                      nullable=False)
    id_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    mensaje: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(Enum("pendiente", "enviada", name="estado_notificacion"),
                                        nullable=False, default="pendiente")


class NotificacionIn(BaseModel):
    id_usuario: int
    tipo: Literal["reserva", "pago", "expiracion", "evento", "credito"]
    id_referencia: int
    mensaje: str = Field(min_length=1, max_length=255)


def _salida(n: Notificacion) -> dict:
    return {"id_notificacion": n.id_notificacion, "tipo": n.tipo, "id_referencia": n.id_referencia,
            "mensaje": n.mensaje, "fecha_envio": n.fecha_envio, "estado": n.estado}


router = APIRouter()


@router.get("/notificaciones/mis", tags=["Notificaciones"], summary="Mis notificaciones recientes")
def mis(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    lista = db.scalars(select(Notificacion).where(Notificacion.id_usuario == info["id_usuario"])
                       .order_by(Notificacion.id_notificacion.desc()).limit(40)).all()
    pendientes = db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.id_usuario == info["id_usuario"], Notificacion.estado == "pendiente"))
    return {"pendientes": pendientes, "items": [_salida(n) for n in lista]}


@router.post("/notificaciones/marcar-enviadas", tags=["Notificaciones"],
             summary="Marca como entregadas (enviada) las notificaciones pendientes del usuario")
def marcar(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    res = db.execute(update(Notificacion).where(Notificacion.id_usuario == info["id_usuario"],
                                                Notificacion.estado == "pendiente")
                     .values(estado="enviada", fecha_envio=utcnow()))
    db.commit()
    return {"marcadas": res.rowcount}


@router.post("/internal/notificaciones", status_code=201, include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_crear(datos: NotificacionIn, db: Session = Depends(get_db)):
    n = Notificacion(**datos.model_dump(), estado="pendiente")
    db.add(n)
    db.commit()
    return _salida(n)


app = crear_app("notificaciones", "Microservicio de Notificaciones",
                "Informa al usuario los hechos relevantes: reserva, pago y vencimiento (RF-NOT-01 a 03).",
                router, Base, engine, preparar)
