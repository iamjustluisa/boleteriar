"""Microservicio de Compras · esquema_compras (Tabla 56) · RF-COM-01 a 03.

Una compra nace de una reserva activa en estado *pendiente* de pago. Una reserva solo se
convierte en compra una vez (UNIQUE id_reserva). El valor total es la suma de los precios de
las localidades de sus asientos (RF-COM-02).
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, Numeric, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app
from common.auth import es_admin, requiere, sesion_actual
from common.clients import asientos, eventos, ids_param, localidades, parse_ids, reservas
from common.errors import ServicioNoDisponible
from common.security import exigir_clave_interna, utcnow

from .database import Base, engine, get_db, preparar


class Compra(Base):
    __tablename__ = "compra"
    __table_args__ = (CheckConstraint("valor_total >= 0", name="ck_compra_valor_total"),)

    id_compra: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)          # RL -> Usuarios
    id_reserva: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)         # RL -> Reservas
    fecha_compra: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum("pendiente", "pagada", "rechazada", name="estado_compra"), nullable=False, default="pendiente")


class CompraIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_reserva: int


class EstadoIn(BaseModel):
    estado: Literal["pagada", "rechazada"]
    valor_total: Decimal | None = None


router = APIRouter()


def cotizar(reserva: dict) -> dict:
    """Precio de cada asiento según su localidad (precio vigente) y total."""
    sillas = asientos.get("/internal/asientos", ids=ids_param(reserva["asientos"]))
    locs = {l["id_localidad"]: l for l in localidades.get(
        "/internal/localidades", ids=ids_param({a["id_localidad"] for a in sillas}))}
    items = []
    for a in sillas:
        l = locs[a["id_localidad"]]
        items.append({"id_asiento": a["id_asiento"], "fila": a["fila"], "numero": a["numero"],
                      "id_localidad": l["id_localidad"], "localidad": l["nombre"], "precio": float(l["precio"])})
    items.sort(key=lambda x: (x["localidad"], x["fila"], x["numero"]))
    return {"items": items, "total": round(sum(i["precio"] for i in items), 2)}


def _salida(c: Compra, evento: dict | None = None, items: list | None = None) -> dict:
    return {"id_compra": c.id_compra, "id_usuario": c.id_usuario, "id_reserva": c.id_reserva,
            "fecha_compra": c.fecha_compra, "valor_total": float(c.valor_total), "estado": c.estado,
            "evento": evento, "items": items}


def _enriquecer(lista: list[Compra]) -> list[dict]:
    if not lista:
        return []
    try:
        res = {r: reservas.get(f"/internal/reservas/{r}") for r in {c.id_reserva for c in lista}}
        evs = {e["id_evento"]: e for e in eventos.get(
            "/internal/eventos", ids=ids_param({r["id_evento"] for r in res.values()}))}
    except ServicioNoDisponible:
        res, evs = {}, {}
    salida = []
    for c in lista:
        r = res.get(c.id_reserva, {})
        d = _salida(c, evs.get(r.get("id_evento")))
        d["cantidad"] = len(r.get("asientos", []))
        salida.append(d)
    return salida


@router.post("/compras", status_code=201, tags=["Compras"],
             summary="RF-COM-01 Registrar una compra a partir de una reserva activa")
def crear(datos: CompraIn, info: dict = Depends(requiere("comprar_boletas")), db: Session = Depends(get_db)):
    reserva = reservas.get_o_none(f"/internal/reservas/{datos.id_reserva}")
    if reserva is None or reserva["id_usuario"] != info["id_usuario"]:
        raise HTTPException(404, "La reserva no existe")
    existente = db.scalar(select(Compra).where(Compra.id_reserva == datos.id_reserva))
    if existente is not None:
        if existente.estado == "pendiente" and reserva["estado"] == "activa":
            return _salida(existente, None, cotizar(reserva)["items"])  # reintento del mismo checkout
        raise HTTPException(409, f"Esta reserva ya tiene una compra ({existente.estado})")
    if reserva["estado"] != "activa" or reserva["segundos_restantes"] <= 0:
        raise HTTPException(409, "La reserva ya no está activa: vuelve a seleccionar tus asientos")
    ev = eventos.get(f"/internal/eventos/{reserva['id_evento']}")
    if ev["estado"] not in ("programado", "aplazado"):
        raise HTTPException(409, f"El evento está {ev['estado']}: no admite compras")

    cot = cotizar(reserva)
    c = Compra(id_usuario=info["id_usuario"], id_reserva=datos.id_reserva, fecha_compra=utcnow(),
               valor_total=Decimal(str(cot["total"])), estado="pendiente")
    db.add(c)
    try:
        db.commit()
    except IntegrityError:  # dos clics simultáneos sobre la misma reserva
        db.rollback()
        raise HTTPException(409, "Esta reserva ya se convirtió en compra")
    auditoria.registrar("COMPRA_REGISTRADA", "COMPRA", c.id_compra, c.id_usuario,
                        f"reserva {c.id_reserva}, total {c.valor_total}")
    return _salida(c, ev, cot["items"])


@router.get("/compras/mis", tags=["Compras"], summary="Mis compras")
def mis_compras(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    return _enriquecer(db.scalars(select(Compra).where(Compra.id_usuario == info["id_usuario"])
                                  .order_by(Compra.id_compra.desc())).all())


@router.get("/compras/{id_compra}", tags=["Compras"])
def detalle(id_compra: int, info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    c = db.get(Compra, id_compra)
    if c is None or (c.id_usuario != info["id_usuario"] and not es_admin(info)):
        raise HTTPException(404, "La compra no existe")
    reserva = reservas.get(f"/internal/reservas/{c.id_reserva}")
    ev = eventos.get_o_none(f"/internal/eventos/{reserva['id_evento']}")
    return _salida(c, ev, cotizar(reserva)["items"])


@router.get("/historial", tags=["Compras"],
            summary="RF-COM-03 Historial de reservas y compras del usuario (incluye eventos realizados)")
def historial(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    compras_usr = _enriquecer(db.scalars(select(Compra).where(Compra.id_usuario == info["id_usuario"])
                                         .order_by(Compra.id_compra.desc())).all())
    lista_res = reservas.get("/internal/reservas", id_usuario=info["id_usuario"])
    por_reserva = {c["id_reserva"]: c for c in compras_usr}
    for r in lista_res:
        c = por_reserva.get(r["id_reserva"])
        r["compra"] = {"id_compra": c["id_compra"], "estado": c["estado"], "valor_total": c["valor_total"]} if c else None
    total_pagado = round(sum(c["valor_total"] for c in compras_usr if c["estado"] == "pagada"), 2)
    return {"reservas": lista_res, "compras": compras_usr,
            "resumen": {"reservas": len(lista_res), "compras_pagadas": sum(c["estado"] == "pagada" for c in compras_usr),
                        "total_pagado": total_pagado}}


# ---------------- Internas ----------------
@router.get("/internal/compras", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_varios(id_usuario: int | None = None, ids: str = "", estado: str | None = None,
                   db: Session = Depends(get_db)):
    q = select(Compra)
    if id_usuario:
        q = q.where(Compra.id_usuario == id_usuario)
    if ids:
        q = q.where(Compra.id_compra.in_(parse_ids(ids)))
    if estado:
        q = q.where(Compra.estado == estado)
    return [_salida(c) for c in db.scalars(q).all()]


@router.get("/internal/compras/{id_compra}", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_uno(id_compra: int, db: Session = Depends(get_db)):
    c = db.get(Compra, id_compra)
    if c is None:
        raise HTTPException(404, "La compra no existe")
    return _salida(c)


@router.get("/internal/compras/{id_compra}/cotizacion", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_cotizacion(id_compra: int, db: Session = Depends(get_db)):
    c = db.get(Compra, id_compra)
    if c is None:
        raise HTTPException(404, "La compra no existe")
    reserva = reservas.get(f"/internal/reservas/{c.id_reserva}")
    return {**_salida(c), "id_evento": reserva["id_evento"], "reserva_estado": reserva["estado"], **cotizar(reserva)}


@router.post("/internal/compras/{id_compra}/estado", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_estado(id_compra: int, datos: EstadoIn, db: Session = Depends(get_db)):
    """RN17: el estado de la compra queda ligado al del pago. Solo desde 'pendiente'."""
    valores = {"estado": datos.estado}
    if datos.valor_total is not None:
        valores["valor_total"] = datos.valor_total
    res = db.execute(update(Compra).where(Compra.id_compra == id_compra, Compra.estado == "pendiente")
                     .values(**valores))
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "La compra ya no está pendiente")
    db.commit()
    return _salida(db.get(Compra, id_compra))


@router.post("/internal/compras/por-reserva/{id_reserva}/anular", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_anular(id_reserva: int, db: Session = Depends(get_db)):
    res = db.execute(update(Compra).where(Compra.id_reserva == id_reserva, Compra.estado == "pendiente")
                     .values(estado="rechazada"))
    db.commit()
    return {"anuladas": res.rowcount}


app = crear_app("compras", "Microservicio de Compras",
                "Compras a partir de reservas e historial del usuario (RF-COM-01 a 03).",
                router, Base, engine, preparar)
