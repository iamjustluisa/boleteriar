"""Microservicio de Analítica · esquema_analitica (Data Warehouse) · Sprints 7 y 8.

Componente OLAP separado de los 13 microservicios transaccionales (OLTP):
* Un ETL (``analitica/etl.py``) recarga el esquema en estrella a partir de las bases de datos de los
  microservicios, de forma manual (administrador) y programada (cada ANALITICA_ETL_MINUTOS).
* ``GET /analitica/indicadores`` calcula los indicadores del dashboard sobre el Data Warehouse, sin
  cargar las bases transaccionales.
"""
import json
import logging
import os
import threading
import time as _time

from fastapi import APIRouter, Depends
from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from common import auditoria
from common.app import crear_app
from common.auth import requiere

from . import etl
from .database import Base, engine, get_db, preparar
from .modelo import (DimEvento, DimLocalidad, DimTiempo, EtlEjecucion, FactCredito, FactOcupacion, FactReserva,
                     FactVenta)

_log = logging.getLogger("boleteria.analitica")
router = APIRouter()
VENDIDA = ("vigente", "usada")
PERMISO = "consultar_indicadores"


def _f(v) -> float:
    return float(v or 0)


@router.post("/analitica/etl", tags=["ETL"], summary="Ejecuta el ETL y recarga el Data Warehouse")
def ejecutar_etl(info: dict = Depends(requiere(PERMISO))):
    r = etl.ejecutar("manual")
    auditoria.registrar("ETL_EJECUTADO", "DATA_WAREHOUSE", r.get("id_ejecucion"), info["id_usuario"], r.get("estado"))
    return r


@router.get("/analitica/etl/ejecuciones", tags=["ETL"], summary="Bitácora de ejecuciones del ETL")
def ejecuciones(_: dict = Depends(requiere(PERMISO)), db: Session = Depends(get_db)):
    filas = db.scalars(select(EtlEjecucion).order_by(EtlEjecucion.id_ejecucion.desc()).limit(20)).all()
    return [{"id_ejecucion": e.id_ejecucion, "inicio": e.inicio, "fin": e.fin, "estado": e.estado, "origen": e.origen,
             "detalle": json.loads(e.detalle) if e.detalle else None} for e in filas]


@router.get("/analitica/indicadores", tags=["Indicadores"], summary="Indicadores del dashboard (desde el Data Warehouse)")
def indicadores(_: dict = Depends(requiere(PERMISO)), db: Session = Depends(get_db)):
    vendida = FactVenta.estado_boleta.in_(VENDIDA)
    ingresos, boletas, compras = db.execute(select(func.sum(FactVenta.precio), func.count(),
                                                   func.count(distinct(FactVenta.id_compra))).where(vendida)).one()
    canceladas = db.scalar(select(func.count()).select_from(FactVenta).where(FactVenta.estado_boleta == "cancelada"))
    usadas = db.scalar(select(func.count()).select_from(FactVenta).where(FactVenta.estado_boleta == "usada"))
    res_total, res_pagadas, res_expiradas = db.execute(select(
        func.count(), func.sum(FactReserva.pagada),
        func.sum(case((FactReserva.estado == "expirada", 1), else_=0)))).one()
    en_venta = DimEvento.estado.in_(("programado", "aplazado"))
    tot, vend = db.execute(select(func.sum(FactOcupacion.total), func.sum(FactOcupacion.vendidos))
                           .join(DimEvento, DimEvento.sk_evento == FactOcupacion.sk_evento).where(en_venta)).one()
    cred = {(t, c): _f(m) for t, c, m in db.execute(select(FactCredito.tipo, FactCredito.concepto, func.sum(FactCredito.monto))
                                                    .group_by(FactCredito.tipo, FactCredito.concepto))}
    abonado = sum(v for (t, _), v in cred.items() if t == "abono")
    usado = sum(v for (t, _), v in cred.items() if t == "uso")

    ventas_ev = {sk: (_f(i), n) for sk, i, n in db.execute(
        select(FactVenta.sk_evento, func.sum(FactVenta.precio), func.count()).where(vendida).group_by(FactVenta.sk_evento))}
    ocup_ev = {sk: (t, v, r) for sk, t, v, r in db.execute(
        select(FactOcupacion.sk_evento, func.sum(FactOcupacion.total), func.sum(FactOcupacion.vendidos),
               func.sum(FactOcupacion.reservados)).group_by(FactOcupacion.sk_evento))}
    por_evento = []
    for e in db.scalars(select(DimEvento).order_by(DimEvento.fecha)):
        i, n = ventas_ev.get(e.sk_evento, (0.0, 0))
        t, v, r = ocup_ev.get(e.sk_evento, (0, 0, 0))
        por_evento.append({"evento": e.nombre, "fecha": e.fecha, "estado": e.estado, "escenario": e.escenario,
                           "ingresos": i, "boletas": n, "asientos": t or 0, "vendidos": v or 0, "reservados": r or 0,
                           "ocupacion": round((v or 0) / t * 100, 1) if t else 0.0})

    por_localidad = [{"localidad": n, "escenario": es, "boletas": c, "ingresos": _f(i)} for n, es, c, i in db.execute(
        select(DimLocalidad.nombre, DimLocalidad.escenario, func.count(), func.sum(FactVenta.precio))
        .join(FactVenta, FactVenta.sk_localidad == DimLocalidad.sk_localidad).where(vendida)
        .group_by(DimLocalidad.nombre, DimLocalidad.escenario).order_by(func.sum(FactVenta.precio).desc()))]

    por_dia = [{"fecha": f, "boletas": c, "ingresos": _f(i)} for f, c, i in db.execute(
        select(DimTiempo.fecha, func.count(), func.sum(FactVenta.precio))
        .join(FactVenta, FactVenta.sk_tiempo == DimTiempo.sk_tiempo).where(vendida)
        .group_by(DimTiempo.fecha).order_by(DimTiempo.fecha.desc()).limit(30))][::-1]

    por_dia_semana = [{"dia": d, "boletas": c, "ingresos": _f(i)} for d, c, i in db.execute(
        select(DimTiempo.dia_semana, func.count(), func.sum(FactVenta.precio))
        .join(FactVenta, FactVenta.sk_tiempo == DimTiempo.sk_tiempo).where(vendida).group_by(DimTiempo.dia_semana))]

    por_metodo = [{"metodo": m, "compras": c, "ingresos": _f(i)} for m, c, i in db.execute(
        select(FactVenta.metodo_pago, func.count(distinct(FactVenta.id_compra)), func.sum(FactVenta.precio))
        .where(vendida).group_by(FactVenta.metodo_pago))]

    ultima = db.scalar(select(EtlEjecucion).where(EtlEjecucion.estado == "ok").order_by(EtlEjecucion.id_ejecucion.desc()).limit(1))
    return {
        "kpi": {
            "ingresos": _f(ingresos), "boletas_vendidas": boletas, "compras": compras,
            "ticket_promedio": round(_f(ingresos) / compras, 0) if compras else 0.0,
            "boletas_canceladas": canceladas, "boletas_usadas": usadas,
            "reservas": res_total, "conversion": round(_f(res_pagadas) / res_total * 100, 1) if res_total else 0.0,
            "expiracion": round(_f(res_expiradas) / res_total * 100, 1) if res_total else 0.0,
            "ocupacion": round(_f(vend) / _f(tot) * 100, 1) if tot else 0.0,
            "creditos_abonados": abonado, "creditos_usados": usado, "creditos_saldo": abonado - usado,
            "precio_justo": cred.get(("abono", "precio_justo"), 0.0),
        },
        "por_evento": por_evento, "por_localidad": por_localidad, "por_dia": por_dia,
        "por_dia_semana": por_dia_semana, "por_metodo": por_metodo,
        "actualizado": ultima.fin if ultima else None,
    }


def _programar() -> None:
    minutos = float(os.getenv("ANALITICA_ETL_MINUTOS", "10"))
    if minutos <= 0:
        return

    def ciclo():
        _time.sleep(float(os.getenv("ANALITICA_ETL_ESPERA_SEG", "45")))  # deja arrancar a los demás servicios
        while True:
            try:
                etl.ejecutar("programado")
            except Exception:  # noqa: BLE001
                _log.exception("ETL programado falló")
            _time.sleep(minutos * 60)
    threading.Thread(target=ciclo, daemon=True, name="etl-programado").start()


app = crear_app("analitica", "Microservicio de Analítica (Data Warehouse)",
                "ETL hacia un esquema en estrella e indicadores para el dashboard (Sprints 7 y 8).",
                router, Base, engine, preparar, _programar)
