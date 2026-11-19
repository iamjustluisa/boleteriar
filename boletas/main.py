"""Microservicio de Boletas · esquema_boletas (Tabla 58) · RF-BOL-01 a 03.

Se emite una boleta por asiento de una compra pagada (RN18), con código único.
RF-BOL-03 pide impedir más de una boleta **vigente** por asiento y evento: la columna calculada
``vigente_unica`` vale 1 solo cuando la boleta está vigente (NULL en otro caso) y forma parte de
UNIQUE (id_evento, id_asiento, vigente_unica). Así, si un evento se cancela (boletas canceladas y
reembolsadas en créditos) y luego se reactiva, sus asientos pueden venderse de nuevo.
La boleta no guarda el usuario: la propiedad se valida a través de la compra (RNF02).
"""
import io
import re
import secrets
from collections import defaultdict
from decimal import Decimal

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import (CheckConstraint, Computed, Enum, Integer, Numeric, String, UniqueConstraint,
                        select, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app
from common.auth import es_admin, requiere, sesion_actual
from common.clients import asientos, compras, eventos, ids_param, localidades, pagos, usuarios
from common.errors import ServicioNoDisponible
from common.security import exigir_clave_interna

from .database import Base, engine, get_db, preparar

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin caracteres ambiguos (0/O, 1/I)


class Boleta(Base):
    __tablename__ = "boleta"
    __table_args__ = (
        UniqueConstraint("id_evento", "id_asiento", "vigente_unica", name="uq_boleta_vigente_evento_asiento"),
        CheckConstraint("precio >= 0", name="ck_boleta_precio"),
    )
    id_boleta: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_compra: Mapped[int] = mapped_column(Integer, nullable=False, index=True)   # RL -> Compras
    id_evento: Mapped[int] = mapped_column(Integer, nullable=False)               # RL -> Eventos
    id_asiento: Mapped[int] = mapped_column(Integer, nullable=False)              # RL -> Asientos
    codigo_boleta: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Enum("vigente", "usada", "cancelada", name="estado_boleta"),
                                        nullable=False, default="vigente")
    vigente_unica: Mapped[int | None] = mapped_column(
        Integer, Computed("CASE WHEN estado = 'vigente' THEN 1 ELSE NULL END", persisted=True))


class ItemIn(BaseModel):
    id_asiento: int
    precio: Decimal = Field(ge=0)


class GenerarIn(BaseModel):
    id_compra: int
    id_evento: int
    items: list[ItemIn] = Field(min_length=1)


def _codigo() -> str:
    return "BOL-" + "".join(secrets.choice(_ALFABETO) for _ in range(10))


def _salida(b: Boleta) -> dict:
    return {"id_boleta": b.id_boleta, "id_compra": b.id_compra, "id_evento": b.id_evento,
            "id_asiento": b.id_asiento, "codigo_boleta": b.codigo_boleta, "precio": float(b.precio),
            "estado": b.estado}


def _enriquecer(lista: list[Boleta]) -> list[dict]:
    salida = [_salida(b) for b in lista]
    if not salida:
        return salida
    try:
        evs = {e["id_evento"]: e for e in eventos.get("/internal/eventos", ids=ids_param({b.id_evento for b in lista}))}
        sillas = {a["id_asiento"]: a for a in asientos.get("/internal/asientos", ids=ids_param({b.id_asiento for b in lista}))}
        locs = {l["id_localidad"]: l for l in localidades.get(
            "/internal/localidades", ids=ids_param({a["id_localidad"] for a in sillas.values()}))} if sillas else {}
    except ServicioNoDisponible:
        return salida
    for d in salida:
        a = sillas.get(d["id_asiento"], {})
        d["evento"] = evs.get(d["id_evento"])
        d["fila"], d["numero"] = a.get("fila"), a.get("numero")
        d["localidad"] = locs.get(a.get("id_localidad"), {}).get("nombre")
    return salida


def _compras_de(id_usuario: int) -> list[int]:
    return [c["id_compra"] for c in compras.get("/internal/compras", id_usuario=id_usuario)]


router = APIRouter()


@router.get("/boletas/mis", tags=["Boletas"], summary="RF-BOL-02 Consultar mis boletas")
def mis_boletas(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    ids = _compras_de(info["id_usuario"])
    if not ids:
        return []
    return _enriquecer(db.scalars(select(Boleta).where(Boleta.id_compra.in_(ids))
                                  .order_by(Boleta.id_boleta.desc())).all())


@router.get("/boletas/resumen", tags=["Administración"], summary="Ventas por evento (administrador)")
def resumen(_: dict = Depends(requiere("consultar_auditoria")), db: Session = Depends(get_db)):
    grupos: dict[int, dict] = defaultdict(lambda: {"vendidas": 0, "ingresos": 0.0, "usadas": 0, "canceladas": 0})
    for b in db.scalars(select(Boleta)):
        g = grupos[b.id_evento]
        if b.estado == "cancelada":
            g["canceladas"] += 1
            continue
        g["vendidas"] += 1
        g["ingresos"] += float(b.precio)
        g["usadas"] += b.estado == "usada"
    evs = {e["id_evento"]: e for e in eventos.get("/internal/eventos", ids=ids_param(grupos))} if grupos else {}
    filas = [{"id_evento": k, "evento": evs.get(k, {}).get("nombre"), "fecha": evs.get(k, {}).get("fecha"),
              "estado_evento": evs.get(k, {}).get("estado"), **v, "ingresos": round(v["ingresos"], 2)}
             for k, v in grupos.items()]
    filas.sort(key=lambda f: -f["ingresos"])
    return {"eventos": filas, "total_boletas": sum(f["vendidas"] for f in filas),
            "total_ingresos": round(sum(f["ingresos"] for f in filas), 2)}


@router.get("/boletas/qr/{codigo}.svg", tags=["Boletas"], summary="Código QR de una boleta (SVG)")
def qr(codigo: str):
    if not re.fullmatch(r"BOL-[A-Z0-9]{6,36}", codigo):
        raise HTTPException(404, "Código inválido")
    img = qrcode.make(codigo, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/boletas/{codigo}", tags=["Boletas"], summary="Consultar una boleta por su código")
def por_codigo(codigo: str, info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    b = db.scalar(select(Boleta).where(Boleta.codigo_boleta == codigo.strip().upper()))
    if b is None or (not es_admin(info) and b.id_compra not in _compras_de(info["id_usuario"])):
        raise HTTPException(404, "La boleta no existe")
    d = _enriquecer([b])[0]
    if es_admin(info):
        c = compras.get(f"/internal/compras/{b.id_compra}")
        u = usuarios.get_o_none(f"/internal/usuarios/{c['id_usuario']}")
        d["titular"] = f"{u['nombre']} {u['apellido']}" if u else None
    return d


@router.put("/boletas/{codigo}/usar", tags=["Administración"], summary="Marcar una boleta como usada (ingreso)")
def usar(codigo: str, actor: dict = Depends(requiere("gestionar_eventos")), db: Session = Depends(get_db)):
    b = db.scalar(select(Boleta).where(Boleta.codigo_boleta == codigo.strip().upper()))
    if b is None:
        raise HTTPException(404, "La boleta no existe")
    if b.estado != "vigente":
        raise HTTPException(409, f"La boleta ya está {b.estado}")
    b.estado = "usada"
    db.commit()
    auditoria.registrar("BOLETA_USADA", "BOLETA", b.id_boleta, actor["id_usuario"], b.codigo_boleta)
    return _enriquecer([b])[0]


# ---------------- Internas ----------------
@router.post("/internal/boletas/generar", include_in_schema=False, dependencies=[Depends(exigir_clave_interna)])
def interno_generar(datos: GenerarIn, db: Session = Depends(get_db)):
    """RF-BOL-01. Idempotente: si la compra ya tiene boletas, las devuelve."""
    ya = db.scalars(select(Boleta).where(Boleta.id_compra == datos.id_compra)).all()
    if ya:
        return _enriquecer(ya)
    nuevas = [Boleta(id_compra=datos.id_compra, id_evento=datos.id_evento, id_asiento=i.id_asiento,
                     precio=i.precio, codigo_boleta=_codigo(), estado="vigente") for i in datos.items]
    db.add_all(nuevas)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una boleta para uno de estos asientos en este evento")
    for b in nuevas:
        auditoria.registrar("BOLETA_EMITIDA", "BOLETA", b.id_boleta, None,
                            f"{b.codigo_boleta} compra {b.id_compra}")
    return _enriquecer(nuevas)


def _usuarios_de_compras(ids_compra) -> dict[int, int]:
    if not ids_compra:
        return {}
    return {c["id_compra"]: c["id_usuario"] for c in compras.get("/internal/compras", ids=ids_param(ids_compra))}


@router.post("/internal/boletas/cancelar-por-evento/{id_evento}", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_cancelar_evento(id_evento: int, db: Session = Depends(get_db)):
    """Evento cancelado: las boletas vigentes pasan a canceladas y su valor se devuelve en créditos."""
    lista = db.scalars(select(Boleta).where(Boleta.id_evento == id_evento, Boleta.estado == "vigente")).all()
    if not lista:
        return {"total": 0, "creditos": 0, "usuarios": 0}
    for b in lista:
        b.estado = "cancelada"
    db.commit()
    ev = eventos.get_o_none(f"/internal/eventos/{id_evento}") or {"nombre": f"evento {id_evento}"}
    duenos = _usuarios_de_compras({b.id_compra for b in lista})
    r = pagos.post("/internal/creditos/reembolsar", {
        "concepto": "evento_cancelado",
        "mensaje": f"«{ev['nombre']}» fue cancelado. Te devolvimos {{monto}} en créditos para tu próxima compra.",
        "items": [{"id_boleta": b.id_boleta, "id_usuario": duenos[b.id_compra], "monto_base": float(b.precio),
                   "descripcion": f"Evento cancelado: {ev['nombre']} · boleta {b.codigo_boleta}"} for b in lista]})
    return {"total": len(lista), "creditos": r["total"], "usuarios": len(r["usuarios"])}


class PrecioJustoIn(BaseModel):
    id_localidad: int
    precio_nuevo: Decimal = Field(ge=0)


@router.post("/internal/boletas/precio-justo", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_precio_justo(datos: PrecioJustoIn, db: Session = Depends(get_db)):
    """Precio Justo Garantizado: si el precio de una localidad baja, cada boleta vigente de un evento
    que aún no ocurre y que se pagó más cara recibe la diferencia en créditos."""
    sillas = [a["id_asiento"] for a in asientos.get("/internal/asientos", localidades=str(datos.id_localidad))]
    if not sillas:
        return {"boletas": 0, "usuarios": 0, "total": 0}
    candidatas = db.scalars(select(Boleta).where(Boleta.estado == "vigente", Boleta.id_asiento.in_(sillas),
                                                 Boleta.precio > datos.precio_nuevo)).all()
    if not candidatas:
        return {"boletas": 0, "usuarios": 0, "total": 0}
    evs = {e["id_evento"]: e for e in eventos.get("/internal/eventos", ids=ids_param({b.id_evento for b in candidatas}))}
    candidatas = [b for b in candidatas if evs.get(b.id_evento, {}).get("estado") in ("programado", "aplazado")]
    if not candidatas:
        return {"boletas": 0, "usuarios": 0, "total": 0}
    duenos = _usuarios_de_compras({b.id_compra for b in candidatas})
    nombre = localidades.get(f"/internal/localidades/{datos.id_localidad}")["nombre"]
    r = pagos.post("/internal/creditos/reembolsar", {
        "concepto": "precio_justo",
        "mensaje": f"Precio Justo: bajó el precio de la localidad {nombre}. Te devolvimos {{monto}} en créditos.",
        "items": [{"id_boleta": b.id_boleta, "id_usuario": duenos[b.id_compra],
                   "monto_base": float(b.precio - datos.precio_nuevo),
                   "descripcion": f"Precio Justo: {evs[b.id_evento]['nombre']} · {nombre} bajó a "
                                  f"${datos.precio_nuevo:,.0f} · boleta {b.codigo_boleta}"} for b in candidatas]})
    return {"boletas": len(candidatas), "usuarios": len(r["usuarios"]), "total": r["total"]}


@router.get("/internal/boletas/titulares/{id_evento}", include_in_schema=False,
            dependencies=[Depends(exigir_clave_interna)])
def interno_titulares(id_evento: int, db: Session = Depends(get_db)):
    """Usuarios con boletas vigentes del evento (para avisarles si el evento se aplaza)."""
    ids = set(db.scalars(select(Boleta.id_compra).where(Boleta.id_evento == id_evento, Boleta.estado == "vigente")))
    return sorted(set(_usuarios_de_compras(ids).values()))


app = crear_app("boletas", "Microservicio de Boletas",
                "Emisión y consulta de boletas de compras pagadas (RF-BOL-01 a 03).",
                router, Base, engine, preparar)
