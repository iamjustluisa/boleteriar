"""Microservicio de Eventos · esquema_eventos (Tabla 51 + IMAGEN_EVENTO) · RF-EVE-01 a 03.

Estados del evento
------------------
  programado ──(cambia fecha/hora)──► aplazado ──(cambia otra vez)──► aplazado
      │  └──────────────┬──────────────────┘
      │           (cancelar) ──► cancelado ──(editar y reactivar)──► programado / aplazado
      └──(fecha pasada o marcado a mano)──► realizado  (final)

* **aplazado**: se cambió la fecha u hora. Sigue a la venta, las boletas siguen siendo válidas y se
  notifica a quienes ya compraron.
* **cancelado**: no admite reservas ni compras; se cancelan las reservas activas, se anulan las
  boletas y su valor se devuelve en **créditos**; los asientos quedan libres. Se puede **reactivar**
  editándolo (con fecha futura).
* **realizado**: automático cuando la fecha ya pasó; también se puede marcar a mano.
"""
import base64
import binascii
import re
from datetime import date, datetime, time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import (Date, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        Time, func, or_, select, update)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import ahora_local, crear_app, hoy_local
from common.auth import requiere
from common.clients import boletas, disponibilidad, escenarios, ids_param, parse_ids, reservas
from common.errors import ErrorServicio, ServicioNoDisponible
from common.notificar import notificar
from common.security import exigir_clave_interna, utcnow

from .database import Base, engine, get_db, preparar

EN_VENTA = ("programado", "aplazado")
EDITABLES = ("programado", "aplazado", "cancelado")
MAX_IMAGEN = 3 * 1024 * 1024  # 3 MB
_BLOB = LargeBinary().with_variant(MEDIUMBLOB(), "mysql").with_variant(MEDIUMBLOB(), "mariadb")


class Evento(Base):
    __tablename__ = "evento"
    __table_args__ = (Index("ix_evento_estado_fecha", "estado", "fecha"),)

    id_evento: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_escenario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Escenarios
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[time] = mapped_column(Time, nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum("programado", "aplazado", "realizado", "cancelado", name="estado_evento"),
        nullable=False, default="programado")


class ImagenEvento(Base):
    """Imagen (póster) que sube el administrador. Tabla aparte para que listar eventos sea liviano."""
    __tablename__ = "imagen_evento"
    id_evento: Mapped[int] = mapped_column(ForeignKey("evento.id_evento", ondelete="CASCADE"), primary_key=True)
    tipo_mime: Mapped[str] = mapped_column(String(40), nullable=False)
    datos: Mapped[bytes] = mapped_column(_BLOB, nullable=False)
    actualizada: Mapped[datetime] = mapped_column(DateTime, nullable=False)


Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Descripcion = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class EventoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_escenario: int
    nombre: Nombre
    descripcion: Descripcion | None = None
    fecha: date
    hora: time


class EventoUpd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: Nombre
    descripcion: Descripcion | None = None
    fecha: date
    hora: time


class EstadoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estado: Literal["realizado", "cancelado"]


class ImagenIn(BaseModel):
    imagen: str = Field(description="Imagen como data URL: data:image/jpeg;base64,....")


class EscenarioMini(BaseModel):
    id_escenario: int
    nombre: str
    direccion: str
    capacidad: int


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_evento: int
    id_escenario: int
    nombre: str
    descripcion: str | None
    fecha: date
    hora: time
    estado: str
    escenario: EscenarioMini | None = None
    imagen: str | None = None


router = APIRouter()


def _obtener(db: Session, id_evento: int) -> Evento:
    e = db.get(Evento, id_evento)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El evento no existe")
    return e


def _cerrar_pasados(db: Session) -> None:
    """Los eventos cuya fecha ya pasó quedan 'realizado' (su historial se conserva, RN14)."""
    res = db.execute(update(Evento).where(Evento.estado.in_(EN_VENTA), Evento.fecha < hoy_local())
                     .values(estado="realizado"))
    if res.rowcount:
        db.commit()


def _enriquecer(db: Session, lista: list[Evento]) -> list[EventoOut]:
    """Agrega el escenario (microservicio de Escenarios) y la URL de la imagen, si existe."""
    salida = [EventoOut.model_validate(e) for e in lista]
    if not salida:
        return salida
    try:
        mapa = {x["id_escenario"]: x for x in escenarios.get(
            "/internal/escenarios", ids=ids_param(e.id_escenario for e in salida))}
    except ServicioNoDisponible:
        mapa = {}
    imgs = dict(db.execute(select(ImagenEvento.id_evento, ImagenEvento.actualizada)
                           .where(ImagenEvento.id_evento.in_([e.id_evento for e in salida]))).all())
    for e in salida:
        if e.id_escenario in mapa:
            e.escenario = EscenarioMini(**mapa[e.id_escenario])
        if e.id_evento in imgs:
            e.imagen = f"/api/eventos/eventos/{e.id_evento}/imagen?v={int(imgs[e.id_evento].timestamp())}"
    return salida


def _validar_fecha(fecha: date, hora: time) -> None:
    if fecha < hoy_local() or (fecha == hoy_local() and hora <= ahora_local().time()):
        raise HTTPException(422, "La fecha y hora del evento deben ser futuras")


def _publicar(id_evento: int, id_escenario: int) -> dict:
    """RF-DIS-01: crea un registro de disponibilidad por cada asiento del escenario."""
    try:
        return disponibilidad.post("/internal/disponibilidad/publicar",
                                   {"id_evento": id_evento, "id_escenario": id_escenario})
    except (ErrorServicio, ServicioNoDisponible) as exc:
        return {"publicados": 0, "total": 0, "error": str(exc)}


def _avisar_titulares(e: Evento, mensaje: str) -> int:
    try:
        titulares = boletas.get(f"/internal/boletas/titulares/{e.id_evento}")
    except (ErrorServicio, ServicioNoDisponible):
        return 0
    for u in titulares:
        notificar(u, "evento", e.id_evento, mensaje)
    return len(titulares)


def _fmt(fecha: date, hora: time) -> str:
    return f"{fecha.strftime('%d/%m/%Y')} a las {hora.strftime('%H:%M')}"


# ---------------- Consulta (usuarios) ----------------
@router.get("/eventos", response_model=list[EventoOut], tags=["Eventos"],
            summary="RF-EVE-03 Consultar eventos a la venta (programados y aplazados)")
def listar(q: str | None = None, id_escenario: int | None = None, desde: date | None = None,
           hasta: date | None = None, _: dict = Depends(requiere("consultar_eventos")),
           db: Session = Depends(get_db)):
    _cerrar_pasados(db)
    consulta = select(Evento).where(Evento.estado.in_(EN_VENTA), Evento.fecha >= hoy_local())
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Evento.nombre.ilike(patron), Evento.descripcion.ilike(patron)))
    if id_escenario:
        consulta = consulta.where(Evento.id_escenario == id_escenario)
    if desde:
        consulta = consulta.where(Evento.fecha >= desde)
    if hasta:
        consulta = consulta.where(Evento.fecha <= hasta)
    return _enriquecer(db, db.scalars(consulta.order_by(Evento.fecha, Evento.hora)).all())


@router.get("/eventos/todos", response_model=list[EventoOut], tags=["Administración"],
            summary="Todos los eventos, en cualquier estado (administrador)")
def listar_todos(_: dict = Depends(requiere("gestionar_eventos")), db: Session = Depends(get_db)):
    _cerrar_pasados(db)
    return _enriquecer(db, db.scalars(select(Evento).order_by(Evento.fecha.desc(), Evento.hora)).all())


@router.get("/eventos/{id_evento}", response_model=EventoOut, tags=["Eventos"])
def detalle(id_evento: int, _: dict = Depends(requiere("consultar_eventos")),
            db: Session = Depends(get_db)):
    _cerrar_pasados(db)
    return _enriquecer(db, [_obtener(db, id_evento)])[0]


@router.get("/eventos/{id_evento}/imagen", tags=["Eventos"], summary="Imagen del evento (pública)")
def ver_imagen(id_evento: int, db: Session = Depends(get_db)):
    img = db.get(ImagenEvento, id_evento)
    if img is None:
        raise HTTPException(404, "El evento no tiene imagen")
    return Response(img.datos, media_type=img.tipo_mime, headers={"Cache-Control": "public, max-age=604800"})


# ---------------- Administración ----------------
@router.post("/eventos", status_code=201, tags=["Administración"], summary="RF-EVE-01 Registrar evento")
def crear(datos: EventoIn, actor: dict = Depends(requiere("gestionar_eventos")),
          db: Session = Depends(get_db)):
    escenarios.get(f"/internal/escenarios/{datos.id_escenario}")  # 404 si no existe (RN04)
    _validar_fecha(datos.fecha, datos.hora)
    e = Evento(**datos.model_dump(), estado="programado")
    db.add(e)
    db.commit()
    pub = _publicar(e.id_evento, e.id_escenario)
    auditoria.registrar("CREAR_EVENTO", "EVENTO", e.id_evento, actor["id_usuario"],
                        f"{e.nombre} · {pub.get('publicados', 0)} asientos publicados")
    return {**_enriquecer(db, [e])[0].model_dump(mode="json"), "disponibilidad": pub}


@router.put("/eventos/{id_evento}", tags=["Administración"],
            summary="RF-EVE-02 Editar evento: cambiar fecha/hora lo deja APLAZADO; editar uno CANCELADO lo reactiva")
def actualizar(id_evento: int, datos: EventoUpd, actor: dict = Depends(requiere("gestionar_eventos")),
               db: Session = Depends(get_db)):
    e = _obtener(db, id_evento)
    if e.estado not in EDITABLES:
        raise HTTPException(409, f"Un evento {e.estado} no se puede editar")
    anterior = (e.fecha, e.hora)
    cambio_fecha = (datos.fecha, datos.hora) != anterior
    if cambio_fecha or e.estado == "cancelado":
        _validar_fecha(datos.fecha, datos.hora)
    estado_previo = e.estado
    for k, v in datos.model_dump().items():
        setattr(e, k, v)

    accion, notificados, pub = None, 0, None
    if estado_previo == "cancelado":
        e.estado = "aplazado" if cambio_fecha else "programado"
        accion = "reactivado"
    elif cambio_fecha:
        e.estado = "aplazado"
        accion = "aplazado"
    db.commit()

    if accion == "reactivado":
        pub = _publicar(e.id_evento, e.id_escenario)  # asegura los registros de disponibilidad
        auditoria.registrar("REACTIVAR_EVENTO", "EVENTO", e.id_evento, actor["id_usuario"],
                            f"{e.nombre} vuelve como {e.estado} para el {_fmt(e.fecha, e.hora)}")
    elif accion == "aplazado":
        notificados = _avisar_titulares(
            e, f"«{e.nombre}» fue aplazado: nueva fecha {_fmt(e.fecha, e.hora)}. Tu boleta sigue siendo válida.")
        auditoria.registrar("APLAZAR_EVENTO", "EVENTO", e.id_evento, actor["id_usuario"],
                            f"de {_fmt(*anterior)} a {_fmt(e.fecha, e.hora)}")
    else:
        auditoria.registrar("ACTUALIZAR_EVENTO", "EVENTO", e.id_evento, actor["id_usuario"])
    return {**_enriquecer(db, [e])[0].model_dump(mode="json"), "cambio": accion,
            "notificados": notificados, "disponibilidad": pub}


@router.put("/eventos/{id_evento}/estado", tags=["Administración"],
            summary="RF-EVE-02 Cancelar (reembolso en créditos) o marcar como realizado")
def cambiar_estado(id_evento: int, datos: EstadoIn, actor: dict = Depends(requiere("gestionar_eventos")),
                   db: Session = Depends(get_db)):
    e = _obtener(db, id_evento)
    if e.estado not in EN_VENTA:
        raise HTTPException(409, f"El evento ya está {e.estado}")
    e.estado = datos.estado
    db.commit()
    efectos = {}
    if datos.estado == "cancelado":
        # Se cancelan las reservas activas, se anulan las boletas devolviendo su valor en créditos y
        # se liberan los asientos. Los registros se conservan (RN14).
        try:
            efectos["reservas_canceladas"] = reservas.post(f"/internal/reservas/cancelar-por-evento/{id_evento}")["total"]
        except (ErrorServicio, ServicioNoDisponible):
            efectos["reservas_canceladas"] = None
        try:
            r = boletas.post(f"/internal/boletas/cancelar-por-evento/{id_evento}")
            efectos.update(boletas_canceladas=r["total"], creditos_devueltos=r["creditos"],
                           usuarios_reembolsados=r["usuarios"])
        except (ErrorServicio, ServicioNoDisponible):
            efectos["boletas_canceladas"] = None
        try:
            disponibilidad.post(f"/internal/disponibilidad/liberar-evento/{id_evento}")
        except (ErrorServicio, ServicioNoDisponible):
            pass
    auditoria.registrar("CANCELAR_EVENTO" if datos.estado == "cancelado" else "EVENTO_REALIZADO",
                        "EVENTO", id_evento, actor["id_usuario"], e.nombre)
    return {**_enriquecer(db, [e])[0].model_dump(mode="json"), **efectos}


@router.post("/eventos/{id_evento}/publicar", tags=["Administración"],
             summary="RF-DIS-01 Volver a publicar la disponibilidad (asientos nuevos)")
def publicar(id_evento: int, actor: dict = Depends(requiere("gestionar_eventos")),
             db: Session = Depends(get_db)):
    e = _obtener(db, id_evento)
    if e.estado not in EN_VENTA:
        raise HTTPException(409, "Solo se publica la disponibilidad de eventos a la venta")
    pub = disponibilidad.post("/internal/disponibilidad/publicar",
                              {"id_evento": e.id_evento, "id_escenario": e.id_escenario})
    auditoria.registrar("PUBLICAR_DISPONIBILIDAD", "EVENTO", id_evento, actor["id_usuario"],
                        f"{pub['publicados']} nuevos")
    return pub


@router.put("/eventos/{id_evento}/imagen", tags=["Administración"], summary="Subir o reemplazar la imagen del evento")
def subir_imagen(id_evento: int, datos: ImagenIn, actor: dict = Depends(requiere("gestionar_eventos")),
                 db: Session = Depends(get_db)):
    e = _obtener(db, id_evento)
    m = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,(.+)", datos.imagen.strip(), re.S)
    if not m:
        raise HTTPException(422, "La imagen debe ser JPG, PNG o WEBP")
    try:
        crudo = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "La imagen está dañada")
    if len(crudo) > MAX_IMAGEN:
        raise HTTPException(413, "La imagen supera los 3 MB")
    img = db.get(ImagenEvento, id_evento)
    if img is None:
        img = ImagenEvento(id_evento=id_evento, tipo_mime=m.group(1), datos=crudo, actualizada=utcnow())
        db.add(img)
    else:
        img.tipo_mime, img.datos, img.actualizada = m.group(1), crudo, utcnow()
    db.commit()
    auditoria.registrar("IMAGEN_EVENTO", "EVENTO", id_evento, actor["id_usuario"], f"{len(crudo) // 1024} KB")
    return {"imagen": _enriquecer(db, [e])[0].imagen}


@router.delete("/eventos/{id_evento}/imagen", status_code=204, tags=["Administración"],
               summary="Quitar la imagen del evento (vuelve el póster generado)")
def quitar_imagen(id_evento: int, actor: dict = Depends(requiere("gestionar_eventos")),
                  db: Session = Depends(get_db)):
    img = db.get(ImagenEvento, id_evento)
    if img is not None:
        db.delete(img)
        db.commit()
        auditoria.registrar("QUITAR_IMAGEN_EVENTO", "EVENTO", id_evento, actor["id_usuario"])


# ---------------- Internas ----------------
@router.get("/internal/eventos/contar", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_contar(id_escenario: int, db: Session = Depends(get_db)):
    return {"total": db.scalar(select(func.count()).select_from(Evento)
                               .where(Evento.id_escenario == id_escenario))}


@router.get("/internal/eventos", response_model=list[EventoOut], include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_varios(ids: str = "", id_escenario: int | None = None, estado: str | None = None,
                   db: Session = Depends(get_db)):
    _cerrar_pasados(db)
    q = select(Evento)
    if ids:
        q = q.where(Evento.id_evento.in_(parse_ids(ids)))
    if id_escenario:
        q = q.where(Evento.id_escenario == id_escenario)
    if estado == "en_venta":
        q = q.where(Evento.estado.in_(EN_VENTA))
    elif estado:
        q = q.where(Evento.estado == estado)
    return _enriquecer(db, db.scalars(q).all())


@router.get("/internal/eventos/{id_evento}", response_model=EventoOut, include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_uno(id_evento: int, db: Session = Depends(get_db)):
    _cerrar_pasados(db)
    return _enriquecer(db, [_obtener(db, id_evento)])[0]


app = crear_app("eventos", "Microservicio de Eventos",
                "Administrar los eventos (programado, aplazado, cancelado, realizado), su imagen y su consulta "
                "(RF-EVE-01 a 03).", router, Base, engine, preparar)
