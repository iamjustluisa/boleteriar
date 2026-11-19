"""Microservicio de Reservas · esquema_reservas (Tabla 55) · RF-RES-01 a 04.

Una reserva aparta temporalmente asientos de un evento. Es de todo o nada (RF-RES-01): el cambio
de estado lo hace Disponibilidad en una sola transacción. Si guardar la reserva falla después de
apartar los asientos, se compensa liberándolos (patrón saga). Las reservas vencidas las expira un
proceso en segundo plano (RF-RES-04, RN16).
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from common import auditoria
from common.app import crear_app
from common.auth import es_admin, requiere, sesion_actual
from common.clients import asientos, compras, disponibilidad, eventos, ids_param, localidades
from common.config import settings
from common.errors import ErrorServicio, ServicioNoDisponible
from common.notificar import notificar
from common.security import exigir_clave_interna, utcnow

from .database import Base, SessionLocal, engine, get_db, preparar

_log = logging.getLogger("boleteria.reservas")


class Reserva(Base):
    __tablename__ = "reserva"
    __table_args__ = (Index("ix_reserva_estado_vencimiento", "estado", "fecha_vencimiento"),)

    id_reserva: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Usuarios
    id_evento: Mapped[int] = mapped_column(Integer, nullable=False, index=True)   # RL -> Eventos
    fecha_reserva: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_vencimiento: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum("activa", "cancelada", "expirada", "completada", name="estado_reserva"),
        nullable=False, default="activa")
    detalles: Mapped[list["DetalleReserva"]] = relationship(lazy="selectin", cascade="save-update, merge")


class DetalleReserva(Base):
    __tablename__ = "detalle_reserva"
    id_reserva: Mapped[int] = mapped_column(
        ForeignKey("reserva.id_reserva", ondelete="RESTRICT"), primary_key=True)
    id_asiento: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)  # RL -> Asientos


class ReservaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_evento: int
    asientos: list[int] = Field(min_length=1)


router = APIRouter()


# ---------------- utilidades ----------------
def _segundos_restantes(r: Reserva) -> int:
    if r.estado != "activa":
        return 0
    return max(0, int((r.fecha_vencimiento - utcnow()).total_seconds()))


def _enriquecer(lista: list[Reserva]) -> list[dict]:
    """Agrega datos del evento y de cada asiento (fila, número, localidad y precio)."""
    if not lista:
        return []
    ids_ev = {r.id_evento for r in lista}
    ids_as = {d.id_asiento for r in lista for d in r.detalles}
    try:
        evs = {e["id_evento"]: e for e in eventos.get("/internal/eventos", ids=ids_param(ids_ev))}
        sillas = {a["id_asiento"]: a for a in asientos.get("/internal/asientos", ids=ids_param(ids_as))} \
            if ids_as else {}
        locs = {l["id_localidad"]: l for l in localidades.get(
            "/internal/localidades", ids=ids_param({a["id_localidad"] for a in sillas.values()}))} \
            if sillas else {}
    except ServicioNoDisponible:
        evs, sillas, locs = {}, {}, {}
    salida = []
    for r in lista:
        detalle = []
        for d in r.detalles:
            a = sillas.get(d.id_asiento, {})
            l = locs.get(a.get("id_localidad"), {})
            detalle.append({"id_asiento": d.id_asiento, "fila": a.get("fila"), "numero": a.get("numero"),
                            "id_localidad": a.get("id_localidad"), "localidad": l.get("nombre"),
                            "precio": l.get("precio")})
        detalle.sort(key=lambda x: (x["localidad"] or "", x["fila"] or "", x["numero"] or 0))
        ev = evs.get(r.id_evento)
        salida.append({
            "id_reserva": r.id_reserva, "id_usuario": r.id_usuario, "id_evento": r.id_evento,
            "fecha_reserva": r.fecha_reserva, "fecha_vencimiento": r.fecha_vencimiento,
            "estado": r.estado, "segundos_restantes": _segundos_restantes(r),
            "evento": ev, "asientos": detalle,
            "total": round(sum(float(x["precio"] or 0) for x in detalle), 2),
        })
    return salida


def _bloquear(db: Session, id_reserva: int) -> Reserva:
    r = db.scalar(select(Reserva).where(Reserva.id_reserva == id_reserva).with_for_update())
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La reserva no existe")
    return r


def _cambiar_asientos(id_evento: int, ids: list[int], desde: str, hacia: str, tolerante: bool) -> None:
    try:
        disponibilidad.post("/internal/disponibilidad/cambiar",
                            {"id_evento": id_evento, "asientos": ids, "desde": desde, "hacia": hacia})
    except ErrorServicio as e:
        if not (tolerante and e.status == 409):
            raise
        for i in ids:  # liberar uno por uno los que sí estén en el estado esperado
            try:
                disponibilidad.post("/internal/disponibilidad/cambiar",
                                    {"id_evento": id_evento, "asientos": [i], "desde": desde, "hacia": hacia})
            except ErrorServicio:
                pass


def _liberar(db: Session, r: Reserva, nuevo_estado: str) -> None:
    """Pasa una reserva activa (ya bloqueada) a cancelada/expirada liberando sus asientos (RN13)."""
    _cambiar_asientos(r.id_evento, [d.id_asiento for d in r.detalles], "reservado", "disponible", tolerante=True)
    r.estado = nuevo_estado
    db.commit()
    try:  # una compra pendiente de esta reserva ya no podrá pagarse
        compras.post(f"/internal/compras/por-reserva/{r.id_reserva}/anular")
    except (ErrorServicio, ServicioNoDisponible):
        pass


def expirar_vencidas() -> int:
    """RF-RES-04: reservas activas cuyo tiempo límite pasó → expirada (libera asientos)."""
    n = 0
    with SessionLocal() as db:
        ids = db.scalars(select(Reserva.id_reserva).where(
            Reserva.estado == "activa", Reserva.fecha_vencimiento < utcnow())).all()
        for id_reserva in ids:
            try:
                r = _bloquear(db, id_reserva)
                if r.estado != "activa":
                    db.rollback()
                    continue
                _liberar(db, r, "expirada")
                n += 1
                notificar(r.id_usuario, "expiracion", r.id_reserva,
                          f"Tu reserva #{r.id_reserva} expiró y sus asientos se liberaron.")
                auditoria.registrar("RESERVA_EXPIRADA", "RESERVA", r.id_reserva, r.id_usuario)
            except Exception as exc:
                db.rollback()
                _log.warning("No se pudo expirar la reserva %s: %s", id_reserva, exc)
    return n


def _ciclo_expiracion() -> None:
    while True:
        time.sleep(settings.expiracion_intervalo_seg)
        try:
            expirar_vencidas()
        except Exception as exc:
            _log.warning("Ciclo de expiración: %s", exc)


def _iniciar_expiracion() -> None:
    threading.Thread(target=_ciclo_expiracion, daemon=True, name="expiracion-reservas").start()


# ---------------- Rutas del usuario ----------------
@router.post("/reservas", status_code=201, tags=["Reservas"],
             summary="RF-RES-01 Reservar uno o varios asientos (todo o nada)")
def crear(datos: ReservaIn, info: dict = Depends(requiere("reservar_asientos")),
          db: Session = Depends(get_db)):
    ids = sorted(set(datos.asientos))
    if len(ids) > settings.reserva_max_asientos:
        raise HTTPException(422, f"Puedes reservar máximo {settings.reserva_max_asientos} asientos por reserva")
    ev = eventos.get(f"/internal/eventos/{datos.id_evento}")
    if ev["estado"] not in ("programado", "aplazado"):
        raise HTTPException(409, f"El evento está {ev['estado']}: no admite reservas")

    try:
        disponibilidad.post("/internal/disponibilidad/cambiar", {
            "id_evento": datos.id_evento, "asientos": ids, "desde": "disponible", "hacia": "reservado"})
    except ErrorServicio as e:
        if e.status == 409:
            raise HTTPException(409, {"mensaje": "Uno o más asientos acaban de ser tomados por otra persona. "
                                                 "No se reservó ninguno.",
                                      "asientos": (e.datos or {}).get("asientos", [])})
        raise

    ahora = utcnow()
    r = Reserva(id_usuario=info["id_usuario"], id_evento=datos.id_evento, fecha_reserva=ahora,
                fecha_vencimiento=ahora + timedelta(minutes=settings.reserva_minutos), estado="activa")
    r.detalles = [DetalleReserva(id_asiento=i) for i in ids]
    db.add(r)
    try:
        db.commit()
    except Exception:
        db.rollback()  # compensación: devolver los asientos
        _cambiar_asientos(datos.id_evento, ids, "reservado", "disponible", tolerante=True)
        raise HTTPException(503, "No se pudo guardar la reserva; los asientos se liberaron")

    notificar(r.id_usuario, "reserva", r.id_reserva,
              f"Reservaste {len(ids)} asiento(s) para «{ev['nombre']}». "
              f"Tienes {int(settings.reserva_minutos)} minutos para completar la compra.")
    auditoria.registrar("RESERVA_CREADA", "RESERVA", r.id_reserva, r.id_usuario,
                        f"evento {r.id_evento}, asientos {ids}")
    return _enriquecer([r])[0]


@router.get("/reservas/mis", tags=["Reservas"], summary="RF-RES-02 Consultar mis reservas")
def mis_reservas(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    lista = db.scalars(select(Reserva).where(Reserva.id_usuario == info["id_usuario"])
                       .order_by(Reserva.id_reserva.desc())).all()
    return _enriquecer(lista)


@router.get("/reservas", tags=["Administración"], summary="Reservas del sistema (administrador)")
def todas(estado: str | None = None, limit: int = 100, _: dict = Depends(requiere("gestionar_eventos")),
          db: Session = Depends(get_db)):
    q = select(Reserva).order_by(Reserva.id_reserva.desc()).limit(min(limit, 500))
    if estado:
        q = q.where(Reserva.estado == estado)
    return _enriquecer(db.scalars(q).all())


@router.get("/reservas/{id_reserva}", tags=["Reservas"])
def detalle(id_reserva: int, info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    r = db.get(Reserva, id_reserva)
    if r is None or (r.id_usuario != info["id_usuario"] and not es_admin(info)):
        raise HTTPException(404, "La reserva no existe")  # no revela reservas de otros (RNF02)
    return _enriquecer([r])[0]


@router.put("/reservas/{id_reserva}/cancelar", tags=["Reservas"],
            summary="RF-RES-03 Cancelar una reserva activa liberando sus asientos")
def cancelar(id_reserva: int, info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    r = _bloquear(db, id_reserva)
    if r.id_usuario != info["id_usuario"] and not es_admin(info):
        db.rollback()
        raise HTTPException(404, "La reserva no existe")
    if r.estado != "activa":
        db.rollback()
        raise HTTPException(409, f"La reserva ya está {r.estado}")
    _liberar(db, r, "cancelada")
    auditoria.registrar("RESERVA_CANCELADA", "RESERVA", r.id_reserva, info["id_usuario"])
    return _enriquecer([r])[0]


# ---------------- Internas ----------------
@router.post("/internal/reservas/expirar", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_expirar():
    return {"expiradas": expirar_vencidas()}


@router.get("/internal/reservas", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_por_usuario(id_usuario: int, db: Session = Depends(get_db)):
    return _enriquecer(db.scalars(select(Reserva).where(Reserva.id_usuario == id_usuario)
                                  .order_by(Reserva.id_reserva.desc())).all())


@router.get("/internal/reservas/{id_reserva}", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_uno(id_reserva: int, db: Session = Depends(get_db)):
    r = db.get(Reserva, id_reserva)
    if r is None:
        raise HTTPException(404, "La reserva no existe")
    return {"id_reserva": r.id_reserva, "id_usuario": r.id_usuario, "id_evento": r.id_evento,
            "estado": r.estado, "fecha_vencimiento": r.fecha_vencimiento,
            "segundos_restantes": _segundos_restantes(r), "asientos": [d.id_asiento for d in r.detalles]}


@router.post("/internal/reservas/{id_reserva}/completar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_completar(id_reserva: int, db: Session = Depends(get_db)):
    """Pago aprobado: la reserva pasa a completada y sus asientos a vendido (RN13)."""
    r = _bloquear(db, id_reserva)
    if r.estado != "activa":
        db.rollback()
        raise HTTPException(409, f"La reserva ya no está activa (está {r.estado})")
    if utcnow() > r.fecha_vencimiento:
        _liberar(db, r, "expirada")
        notificar(r.id_usuario, "expiracion", r.id_reserva,
                  f"Tu reserva #{r.id_reserva} expiró antes del pago y sus asientos se liberaron.")
        auditoria.registrar("RESERVA_EXPIRADA", "RESERVA", r.id_reserva, r.id_usuario)
        raise HTTPException(409, "La reserva expiró antes de completar el pago")
    try:
        _cambiar_asientos(r.id_evento, [d.id_asiento for d in r.detalles], "reservado", "vendido",
                          tolerante=False)
    except Exception:
        db.rollback()
        raise
    r.estado = "completada"
    db.commit()
    return {"id_reserva": r.id_reserva, "estado": r.estado}


@router.post("/internal/reservas/{id_reserva}/liberar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_liberar(id_reserva: int, db: Session = Depends(get_db)):
    """Pago rechazado (RN17): la reserva se cancela y los asientos vuelven a disponible."""
    r = _bloquear(db, id_reserva)
    if r.estado != "activa":
        db.rollback()
        return {"id_reserva": r.id_reserva, "estado": r.estado}
    _liberar(db, r, "cancelada")
    return {"id_reserva": r.id_reserva, "estado": r.estado}


@router.post("/internal/reservas/cancelar-por-evento/{id_evento}", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_cancelar_evento(id_evento: int, db: Session = Depends(get_db)):
    n = 0
    for id_reserva in db.scalars(select(Reserva.id_reserva).where(
            Reserva.id_evento == id_evento, Reserva.estado == "activa")).all():
        r = _bloquear(db, id_reserva)
        if r.estado == "activa":
            _liberar(db, r, "cancelada")
            notificar(r.id_usuario, "reserva", r.id_reserva,
                      f"Tu reserva #{r.id_reserva} se canceló porque el evento fue cancelado.")
            n += 1
        else:
            db.rollback()
    return {"total": n}


app = crear_app("reservas", "Microservicio de Reservas",
                "Apartado temporal de asientos por parte de los usuarios (RF-RES-01 a 04).",
                router, Base, engine, preparar, al_iniciar=_iniciar_expiracion)
