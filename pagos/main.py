"""Microservicio de Pagos · esquema_pagos (Tabla 57 + extensión CREDITO) · RF-PAG-01 a 03.

Pago **simulado** (no hay pasarela real, ver alcance). Este servicio orquesta la confirmación:

  aprobado  → Reservas completa la reserva (asientos a *vendido*) → Compra *pagada* →
              Boletas emite una boleta por asiento → notificación al usuario.
  rechazado → Compra *rechazada* → Reservas libera los asientos (RN17) → sin boletas (RN18).

Créditos (monedero del usuario)
-------------------------------
* Se abonan automáticamente cuando un evento se **cancela** (valor de las boletas) y con el
  **Precio Justo Garantizado** (si el precio de una localidad baja después de la compra, se abona
  la diferencia).
* Se usan como medio de pago: solos (si cubren el total) o combinados con tarjeta (pago *mixto*).
* El saldo es la suma de abonos menos usos; cada movimiento queda registrado.

Tarjeta de prueba que siempre se rechaza: **4000 0000 0000 0002**. Cualquier otra tarjeta válida
(algoritmo de Luhn) se aprueba. Nunca se guarda el número de la tarjeta.
"""
import re
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (CheckConstraint, DateTime, Enum, Integer, Numeric, String, case, func,
                        select)
from sqlalchemy.orm import Mapped, Session, mapped_column

from common import auditoria
from common.app import crear_app, hoy_local
from common.auth import es_admin, requiere, sesion_actual
from common.clients import boletas, compras, eventos, reservas
from common.errors import ErrorServicio, ServicioNoDisponible
from common.notificar import notificar
from common.security import exigir_clave_interna, utcnow

from .database import Base, engine, get_db, preparar

TARJETA_RECHAZO = "4000000000000002"
ESTADOS_VENTA = ("programado", "aplazado")
CERO = Decimal("0.00")


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Pago(Base):
    __tablename__ = "pago"
    __table_args__ = (CheckConstraint("valor >= 0", name="ck_pago_valor"),
                      CheckConstraint("valor_creditos >= 0", name="ck_pago_valor_creditos"))

    id_pago: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_compra: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # RL -> Compras
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_pago: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    estado: Mapped[str] = mapped_column(Enum("aprobado", "rechazado", name="estado_pago"), nullable=False)
    referencia: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    metodo: Mapped[str] = mapped_column(Enum("tarjeta", "creditos", "mixto", name="metodo_pago"),
                                        nullable=False, default="tarjeta", server_default="tarjeta")
    valor_creditos: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=CERO,
                                                    server_default="0")


class Credito(Base):
    """Movimiento del monedero de créditos de un usuario (abono o uso)."""
    __tablename__ = "credito"
    __table_args__ = (CheckConstraint("monto > 0", name="ck_credito_monto"),)

    id_credito: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)   # RL -> Usuarios
    tipo: Mapped[str] = mapped_column(Enum("abono", "uso", name="tipo_credito"), nullable=False)
    concepto: Mapped[str] = mapped_column(
        Enum("evento_cancelado", "precio_justo", "pago_compra", name="concepto_credito"), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    id_referencia: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # boleta o compra
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _luhn(numero: str) -> bool:
    total, alt = 0, False
    for d in reversed(numero):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


class PagoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_compra: int
    usar_creditos: bool = False
    titular: str | None = Field(default=None, min_length=3, max_length=80)
    numero_tarjeta: str | None = None
    vencimiento: str | None = Field(default=None, description="MM/AA")
    cvv: str | None = None

    @field_validator("numero_tarjeta")
    @classmethod
    def _tarjeta(cls, v):
        if v is None:
            return v
        v = re.sub(r"[\s-]", "", v)
        if not v.isdigit() or not 13 <= len(v) <= 19 or not _luhn(v):
            raise ValueError("El número de tarjeta no es válido")
        return v

    @field_validator("vencimiento")
    @classmethod
    def _venc(cls, v):
        if v is None:
            return v
        m = re.fullmatch(r"\s*(\d{2})\s*/\s*(\d{2})\s*", v)
        if not m or not 1 <= int(m.group(1)) <= 12:
            raise ValueError("Usa el formato MM/AA")
        mes, anio = int(m.group(1)), 2000 + int(m.group(2))
        hoy = hoy_local()
        if (anio, mes) < (hoy.year, hoy.month):
            raise ValueError("La tarjeta está vencida")
        return f"{mes:02d}/{anio % 100:02d}"

    @field_validator("cvv")
    @classmethod
    def _cvv(cls, v):
        if v is None:
            return v
        if not re.fullmatch(r"\d{3,4}", v.strip()):
            raise ValueError("El CVV debe tener 3 o 4 dígitos")
        return v.strip()


class ItemReembolso(BaseModel):
    id_boleta: int
    id_usuario: int
    monto_base: Decimal = Field(ge=0)
    descripcion: str = Field(max_length=255)


class ReembolsoIn(BaseModel):
    concepto: Literal["evento_cancelado", "precio_justo"]
    items: list[ItemReembolso]
    mensaje: str = Field(default="Recibiste {monto} en créditos.", max_length=220,
                         description="Texto de la notificación; {monto} se reemplaza por el valor abonado")


def _salida(p: Pago) -> dict:
    return {"id_pago": p.id_pago, "id_compra": p.id_compra, "valor": float(p.valor),
            "fecha_pago": p.fecha_pago, "estado": p.estado, "referencia": p.referencia,
            "metodo": p.metodo, "valor_creditos": float(p.valor_creditos or 0)}


def _mov(c: Credito) -> dict:
    return {"id_credito": c.id_credito, "tipo": c.tipo, "concepto": c.concepto, "monto": float(c.monto),
            "id_referencia": c.id_referencia, "descripcion": c.descripcion, "fecha": c.fecha}


def saldo(db: Session, id_usuario: int, bloquear: bool = False) -> Decimal:
    if bloquear:  # bloquea los movimientos del usuario para que dos pagos no gasten el mismo saldo
        db.execute(select(Credito.id_credito).where(Credito.id_usuario == id_usuario).with_for_update()).all()
    total = db.scalar(select(func.coalesce(func.sum(
        case((Credito.tipo == "abono", Credito.monto), else_=-Credito.monto)), 0))
        .where(Credito.id_usuario == id_usuario))
    return _d(total or 0)


def _ya_abonado(db: Session, id_boleta: int, concepto: str) -> Decimal:
    return _d(db.scalar(select(func.coalesce(func.sum(Credito.monto), 0)).where(
        Credito.tipo == "abono", Credito.concepto == concepto, Credito.id_referencia == id_boleta)) or 0)


router = APIRouter()


def _nuevo_pago(id_compra: int, valor, estado: str, metodo: str, valor_creditos=CERO) -> Pago:
    return Pago(id_compra=id_compra, valor=_d(valor), fecha_pago=utcnow(), estado=estado, metodo=metodo,
                valor_creditos=_d(valor_creditos), referencia=f"PAY-{uuid.uuid4().hex[:16].upper()}")


@router.post("/pagos", status_code=201, tags=["Pagos"],
             summary="RF-PAG-01 Registrar el pago (simulado) de una compra, con tarjeta, créditos o ambos")
def pagar(datos: PagoIn, info: dict = Depends(requiere("comprar_boletas")), db: Session = Depends(get_db)):
    compra = compras.get_o_none(f"/internal/compras/{datos.id_compra}")
    if compra is None or compra["id_usuario"] != info["id_usuario"]:
        raise HTTPException(404, "La compra no existe")
    if compra["estado"] != "pendiente":
        raise HTTPException(409, f"La compra ya está {compra['estado']}")
    cot = compras.get(f"/internal/compras/{datos.id_compra}/cotizacion")
    ev = eventos.get(f"/internal/eventos/{cot['id_evento']}")
    if ev["estado"] not in ESTADOS_VENTA:
        raise HTTPException(409, f"El evento está {ev['estado']}: no se puede pagar")

    id_usr, id_res = info["id_usuario"], compra["id_reserva"]
    total = _d(cot["total"])
    usar = min(saldo(db, id_usr), total) if datos.usar_creditos else CERO
    resto = total - usar
    metodo = "creditos" if resto == 0 else ("mixto" if usar > 0 else "tarjeta")
    if resto > 0 and not (datos.titular and datos.numero_tarjeta and datos.vencimiento and datos.cvv):
        raise HTTPException(422, f"Faltan los datos de la tarjeta para pagar {resto:,.0f} COP")

    # ---------- Pago rechazado (RN17): no se consume ningún crédito ----------
    if resto > 0 and datos.numero_tarjeta == TARJETA_RECHAZO:
        p = _nuevo_pago(datos.id_compra, total, "rechazado", metodo)
        db.add(p)
        db.commit()
        compras.post(f"/internal/compras/{datos.id_compra}/estado", {"estado": "rechazada"})
        reservas.post(f"/internal/reservas/{id_res}/liberar")
        notificar(id_usr, "pago", datos.id_compra,
                  f"El pago de tu compra #{datos.id_compra} fue rechazado; los asientos se liberaron.")
        auditoria.registrar("PAGO_RECHAZADO", "PAGO", p.id_pago, id_usr, f"compra {datos.id_compra}")
        return {**_salida(p), "boletas": [],
                "mensaje": "El banco rechazó el pago. Los asientos se liberaron y no se usaron tus créditos."}

    # ---------- Pago aprobado ----------
    # Primero se asegura la venta de los asientos; si la reserva expiró no se cobra nada.
    try:
        reservas.post(f"/internal/reservas/{id_res}/completar")
    except ErrorServicio as e:
        if e.status == 409:  # expirada/cancelada: Reservas ya anuló la compra pendiente
            raise HTTPException(409, f"{e.detalle}. No se realizó ningún cobro.")
        raise
    if usar > 0:  # el uso de créditos y el pago se guardan en la misma transacción
        disponible = saldo(db, id_usr, bloquear=True)
        usar = min(usar, disponible)
        db.add(Credito(id_usuario=id_usr, tipo="uso", concepto="pago_compra", monto=usar,
                       id_referencia=datos.id_compra, descripcion=f"Pago de la compra #{datos.id_compra} · {ev['nombre']}"[:255],
                       fecha=utcnow()))
    p = _nuevo_pago(datos.id_compra, total, "aprobado", metodo, usar)
    db.add(p)
    db.commit()
    compras.post(f"/internal/compras/{datos.id_compra}/estado", {"estado": "pagada", "valor_total": float(total)})
    emitidas, aviso = [], None
    try:
        emitidas = boletas.post("/internal/boletas/generar", {
            "id_compra": datos.id_compra, "id_evento": cot["id_evento"],
            "items": [{"id_asiento": i["id_asiento"], "precio": i["precio"]} for i in cot["items"]]})
    except (ErrorServicio, ServicioNoDisponible) as exc:
        aviso = f"El pago se aprobó pero las boletas aún no se emitieron: {exc}"
    notificar(id_usr, "pago", datos.id_compra,
              f"¡Pago aprobado! Tus {len(emitidas)} boleta(s) para «{ev['nombre']}» ya están disponibles.")
    auditoria.registrar("PAGO_APROBADO", "PAGO", p.id_pago, id_usr,
                        f"compra {datos.id_compra}, valor {total}, método {metodo}, créditos {usar}")
    return {**_salida(p), "boletas": emitidas, "mensaje": aviso or "Pago aprobado",
            "saldo_creditos": float(saldo(db, id_usr))}


@router.get("/pagos/compra/{id_compra}", tags=["Pagos"],
            summary="RF-PAG-02 Estado más reciente del pago de una compra")
def estado_pago(id_compra: int, info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    compra = compras.get_o_none(f"/internal/compras/{id_compra}")
    if compra is None or (compra["id_usuario"] != info["id_usuario"] and not es_admin(info)):
        raise HTTPException(404, "La compra no existe")
    p = db.scalar(select(Pago).where(Pago.id_compra == id_compra).order_by(Pago.id_pago.desc()).limit(1))
    if p is None:
        raise HTTPException(404, "La compra aún no tiene pagos")
    return _salida(p)


@router.get("/pagos", tags=["Administración"], summary="Pagos registrados (administrador)")
def listar(_: dict = Depends(requiere("consultar_auditoria")), db: Session = Depends(get_db)):
    return [_salida(p) for p in db.scalars(select(Pago).order_by(Pago.id_pago.desc()).limit(200))]


# ---------------- Créditos ----------------
@router.get("/creditos/mis", tags=["Créditos"], summary="Saldo y movimientos de mis créditos")
def mis_creditos(info: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    movs = db.scalars(select(Credito).where(Credito.id_usuario == info["id_usuario"])
                      .order_by(Credito.id_credito.desc()).limit(100)).all()
    return {"saldo": float(saldo(db, info["id_usuario"])), "movimientos": [_mov(c) for c in movs]}


@router.get("/creditos/resumen", tags=["Administración"], summary="Créditos emitidos y usados (administrador)")
def resumen_creditos(_: dict = Depends(requiere("consultar_auditoria")), db: Session = Depends(get_db)):
    filas = db.execute(select(Credito.tipo, Credito.concepto, func.count(), func.sum(Credito.monto))
                       .group_by(Credito.tipo, Credito.concepto)).all()
    return [{"tipo": t, "concepto": c, "movimientos": n, "total": float(s or 0)} for t, c, n, s in filas]


@router.post("/internal/creditos/reembolsar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_reembolsar(datos: ReembolsoIn, db: Session = Depends(get_db)):
    """Abona créditos por boleta. Idempotente y sin dobles reembolsos:
    * evento_cancelado: se devuelve lo pagado por la boleta menos lo ya devuelto por Precio Justo.
    * precio_justo: se devuelve la diferencia de precio menos lo ya devuelto antes por Precio Justo."""
    por_usuario: dict[int, Decimal] = {}
    for it in datos.items:
        ya_pj = _ya_abonado(db, it.id_boleta, "precio_justo")
        if datos.concepto == "evento_cancelado":
            if _ya_abonado(db, it.id_boleta, "evento_cancelado") > 0:
                continue
            monto = _d(it.monto_base) - ya_pj
        else:
            monto = _d(it.monto_base) - ya_pj
        if monto <= 0:
            continue
        db.add(Credito(id_usuario=it.id_usuario, tipo="abono", concepto=datos.concepto, monto=monto,
                       id_referencia=it.id_boleta, descripcion=it.descripcion[:255], fecha=utcnow()))
        por_usuario[it.id_usuario] = por_usuario.get(it.id_usuario, CERO) + monto
    db.commit()
    for u, m in por_usuario.items():
        notificar(u, "credito", 0, datos.mensaje.replace("{monto}", f"${m:,.0f}".replace(",", ".")))
        auditoria.registrar("CREDITOS_ABONADOS", "CREDITO", None, u, f"{datos.concepto}: {m}")
    return {"usuarios": [{"id_usuario": u, "monto": float(m)} for u, m in por_usuario.items()],
            "total": float(sum(por_usuario.values(), CERO))}


app = crear_app("pagos", "Microservicio de Pagos",
                "Pago (simulado) de cada compra con tarjeta o créditos, y monedero de créditos (RF-PAG-01 a 03).",
                router, Base, engine, preparar)
