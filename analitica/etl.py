"""ETL del Data Warehouse (Sprint 7).

Extracción: lee, en modo solo lectura, las bases de datos de los microservicios transaccionales
(cada una con su propia conexión: pueden estar en servidores distintos).
Transformación: une las referencias lógicas entre esquemas (boleta → asiento → localidad, boleta →
compra → usuario y pago), convierte las fechas UTC a la hora local, quita los datos personales y
arma las dimensiones con llaves sustitutas.
Carga: recarga completa del esquema en estrella dentro de una sola transacción y verificación de
calidad (las boletas y el valor vendido del DW deben coincidir con el origen).

Uso:  python -m analitica.etl
"""
import json
import logging
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, text

from common.config import settings
from common.db import build_db
from common.security import utcnow

from .database import SessionLocal
from .modelo import (DimEvento, DimLocalidad, DimTiempo, DimUsuario, EtlEjecucion, FactCredito, FactOcupacion,
                     FactReserva, FactVenta)

_log = logging.getLogger("boleteria.etl")
_lock = threading.Lock()
_fuentes: dict = {}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ---------------------------------------------------------------- extracción
def _fuente(servicio: str):
    if servicio not in _fuentes:
        _fuentes[servicio] = build_db(servicio)[0]
    return _fuentes[servicio]


def _leer(servicio: str, sql: str) -> list[dict]:
    with _fuente(servicio).connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql))]


def extraer() -> dict:
    return {
        "usuarios": _leer("acceso", "SELECT c.id_usuario, r.nombre AS rol FROM credencial c JOIN rol r ON r.id_rol = c.id_rol"),
        "escenarios": _leer("escenarios", "SELECT id_escenario, nombre, capacidad FROM escenario"),
        "eventos": _leer("eventos", "SELECT id_evento, id_escenario, nombre, fecha, hora, estado FROM evento"),
        "localidades": _leer("localidades", "SELECT id_localidad, id_escenario, nombre, precio, capacidad FROM localidad"),
        "asientos": _leer("asientos", "SELECT id_asiento, id_localidad FROM asiento"),
        "disponibilidad": _leer("disponibilidad", "SELECT id_evento, id_asiento, estado FROM disponibilidad_asiento"),
        "reservas": _leer("reservas", "SELECT r.id_reserva, r.id_usuario, r.id_evento, r.fecha_reserva, r.estado, "
                                      "(SELECT COUNT(*) FROM detalle_reserva d WHERE d.id_reserva = r.id_reserva) AS asientos "
                                      "FROM reserva r"),
        "compras": _leer("compras", "SELECT id_compra, id_usuario, id_reserva, fecha_compra, estado FROM compra"),
        "pagos": _leer("pagos", "SELECT id_pago, id_compra, metodo, estado FROM pago"),
        "creditos": _leer("pagos", "SELECT id_credito, id_usuario, tipo, concepto, monto, fecha FROM credito"),
        "boletas": _leer("boletas", "SELECT id_boleta, id_compra, id_evento, id_asiento, precio, estado FROM boleta"),
    }


# ---------------------------------------------------------------- transformación
def _dt(v) -> datetime:
    if isinstance(v, datetime):
        return v
    s = str(v).replace("T", " ")
    return datetime.fromisoformat(s[:26])


def _d(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _t(v) -> time:
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):  # MySQL devuelve TIME como timedelta
        s = int(v.total_seconds())
        return time(s // 3600 % 24, s // 60 % 60, s % 60)
    return time.fromisoformat(str(v)[:8])


def _local(v) -> date:
    """Fecha UTC del origen → fecha local (America/Bogota) para la dimensión tiempo."""
    return _dt(v).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.zona_horaria)).date()


def _sk_tiempo(f: date) -> int:
    return f.year * 10000 + f.month * 100 + f.day


def transformar(o: dict) -> dict:
    esc = {e["id_escenario"]: e for e in o["escenarios"]}
    roles = {u["id_usuario"]: u["rol"] for u in o["usuarios"]}
    loc_de_asiento = {a["id_asiento"]: a["id_localidad"] for a in o["asientos"]}
    compras = {c["id_compra"]: c for c in o["compras"]}
    compra_de_reserva = {c["id_reserva"]: c for c in o["compras"]}
    metodo = {}
    for p in sorted(o["pagos"], key=lambda p: p["id_pago"]):
        if p["estado"] == "aprobado":
            metodo[p["id_compra"]] = p["metodo"]

    dim_evento, sk_evento = [], {}
    for i, e in enumerate(sorted(o["eventos"], key=lambda e: e["id_evento"]), start=1):
        es = esc.get(e["id_escenario"], {"nombre": f"Escenario {e['id_escenario']}", "capacidad": 0})
        sk_evento[e["id_evento"]] = i
        dim_evento.append({"sk_evento": i, "id_evento": e["id_evento"], "nombre": e["nombre"], "fecha": _d(e["fecha"]),
                           "hora": _t(e["hora"]), "estado": e["estado"], "id_escenario": e["id_escenario"],
                           "escenario": es["nombre"], "capacidad_escenario": es["capacidad"]})

    dim_localidad, sk_localidad = [], {}
    for i, l in enumerate(sorted(o["localidades"], key=lambda l: l["id_localidad"]), start=1):
        sk_localidad[l["id_localidad"]] = i
        dim_localidad.append({"sk_localidad": i, "id_localidad": l["id_localidad"], "nombre": l["nombre"],
                              "escenario": esc.get(l["id_escenario"], {}).get("nombre", "—"),
                              "precio_actual": Decimal(str(l["precio"])), "capacidad": l["capacidad"]})

    ids_usuario = set(roles) | {c["id_usuario"] for c in o["compras"]} | {r["id_usuario"] for r in o["reservas"]} \
        | {c["id_usuario"] for c in o["creditos"]}
    sk_usuario = {u: i for i, u in enumerate(sorted(ids_usuario), start=1)}
    dim_usuario = [{"sk_usuario": sk, "id_usuario": u, "rol": roles.get(u, "desconocido")} for u, sk in sk_usuario.items()]

    fechas: set[date] = set()
    fact_venta, omitidas = [], 0
    for b in o["boletas"]:
        c = compras.get(b["id_compra"])
        loc = loc_de_asiento.get(b["id_asiento"])
        if c is None or loc not in sk_localidad or b["id_evento"] not in sk_evento:
            omitidas += 1
            continue
        f = _local(c["fecha_compra"])
        fechas.add(f)
        fact_venta.append({"id_boleta": b["id_boleta"], "sk_tiempo": _sk_tiempo(f), "sk_evento": sk_evento[b["id_evento"]],
                           "sk_localidad": sk_localidad[loc], "sk_usuario": sk_usuario[c["id_usuario"]],
                           "id_compra": b["id_compra"], "precio": Decimal(str(b["precio"])),
                           "estado_boleta": b["estado"], "metodo_pago": metodo.get(b["id_compra"], "tarjeta")})

    fact_reserva = []
    for r in o["reservas"]:
        if r["id_evento"] not in sk_evento:
            continue
        f = _local(r["fecha_reserva"])
        fechas.add(f)
        c = compra_de_reserva.get(r["id_reserva"])
        fact_reserva.append({"id_reserva": r["id_reserva"], "sk_tiempo": _sk_tiempo(f), "sk_evento": sk_evento[r["id_evento"]],
                             "sk_usuario": sk_usuario[r["id_usuario"]], "asientos": int(r["asientos"] or 0),
                             "estado": r["estado"], "pagada": int(bool(c and c["estado"] == "pagada"))})

    conteo: dict[tuple, Counter] = defaultdict(Counter)
    for d in o["disponibilidad"]:
        loc = loc_de_asiento.get(d["id_asiento"])
        if loc in sk_localidad and d["id_evento"] in sk_evento:
            conteo[(sk_evento[d["id_evento"]], sk_localidad[loc])][d["estado"]] += 1
    fact_ocupacion = [{"sk_evento": ev, "sk_localidad": lo, "total": sum(c.values()), "disponibles": c["disponible"],
                       "reservados": c["reservado"], "vendidos": c["vendido"]} for (ev, lo), c in conteo.items()]

    fact_credito = []
    for m in o["creditos"]:
        f = _local(m["fecha"])
        fechas.add(f)
        fact_credito.append({"id_credito": m["id_credito"], "sk_tiempo": _sk_tiempo(f), "sk_usuario": sk_usuario[m["id_usuario"]],
                             "tipo": m["tipo"], "concepto": m["concepto"], "monto": Decimal(str(m["monto"]))})

    dim_tiempo = [{"sk_tiempo": _sk_tiempo(f), "fecha": f, "anio": f.year, "trimestre": (f.month - 1) // 3 + 1,
                   "mes": f.month, "nombre_mes": MESES[f.month - 1], "dia": f.day, "dia_semana": DIAS[f.weekday()],
                   "fin_de_semana": int(f.weekday() >= 5)} for f in sorted(fechas)]

    return {"dim_tiempo": dim_tiempo, "dim_evento": dim_evento, "dim_localidad": dim_localidad, "dim_usuario": dim_usuario,
            "fact_venta": fact_venta, "fact_reserva": fact_reserva, "fact_ocupacion": fact_ocupacion,
            "fact_credito": fact_credito, "_omitidas": omitidas}


# ---------------------------------------------------------------- carga
ORDEN = [(DimTiempo, "dim_tiempo"), (DimEvento, "dim_evento"), (DimLocalidad, "dim_localidad"), (DimUsuario, "dim_usuario"),
         (FactVenta, "fact_venta"), (FactReserva, "fact_reserva"), (FactOcupacion, "fact_ocupacion"), (FactCredito, "fact_credito")]


def cargar(datos: dict) -> dict:
    filas = {}
    with SessionLocal() as db, db.begin():
        for modelo, _ in reversed(ORDEN):  # primero hechos, luego dimensiones (por las FK)
            db.execute(delete(modelo))
        for modelo, clave in ORDEN:
            if datos[clave]:
                db.execute(insert(modelo), datos[clave])
            filas[clave] = len(datos[clave])
    return filas


def verificar(origen: dict, datos: dict) -> dict:
    """Controles de calidad: el DW debe cuadrar con el origen."""
    vendidas_origen = [b for b in origen["boletas"] if b["estado"] in ("vigente", "usada")]
    vendidas_dw = [f for f in datos["fact_venta"] if f["estado_boleta"] in ("vigente", "usada")]
    valor_origen = sum(Decimal(str(b["precio"])) for b in vendidas_origen)
    valor_dw = sum(f["precio"] for f in vendidas_dw)
    asientos_vendidos = sum(f["vendidos"] for f in datos["fact_ocupacion"])
    return {
        "boletas_origen": len(origen["boletas"]), "boletas_dw": len(datos["fact_venta"]),
        "valor_vendido_origen": float(valor_origen), "valor_vendido_dw": float(valor_dw),
        "boletas_vigentes_o_usadas": len(vendidas_dw), "asientos_vendidos": asientos_vendidos,
        "cuadra": len(origen["boletas"]) == len(datos["fact_venta"]) and valor_origen == valor_dw,
    }


def ejecutar(origen_ejecucion: str = "manual") -> dict:
    if not _lock.acquire(blocking=False):
        return {"estado": "en_curso", "detalle": "Ya hay una ejecución del ETL en curso"}
    inicio = utcnow()
    try:
        with SessionLocal() as db:
            ej = EtlEjecucion(inicio=inicio, estado="en_curso", origen=origen_ejecucion)
            db.add(ej)
            db.commit()
            id_ej = ej.id_ejecucion
        try:
            o = extraer()
            datos = transformar(o)
            filas = cargar(datos)
            calidad = verificar(o, datos)
            resultado = {"estado": "ok", "filas": filas, "calidad": calidad, "omitidas": datos["_omitidas"]}
        except Exception as exc:  # se registra el error en la bitácora
            _log.exception("Falló el ETL")
            resultado = {"estado": "error", "error": str(exc)[:500]}
        with SessionLocal() as db:
            ej = db.get(EtlEjecucion, id_ej)
            ej.fin = utcnow()
            ej.estado = resultado["estado"]
            ej.detalle = json.dumps(resultado, ensure_ascii=False)
            db.commit()
        resultado.update(id_ejecucion=id_ej, inicio=inicio.isoformat(), segundos=round((utcnow() - inicio).total_seconds(), 2))
        return resultado
    finally:
        _lock.release()


if __name__ == "__main__":
    from .database import Base, engine, preparar
    preparar()
    Base.metadata.create_all(engine)
    print(json.dumps(ejecutar("consola"), ensure_ascii=False, indent=2, default=str))
