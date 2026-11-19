"""Microservicio de Disponibilidad · esquema_disponibilidad (Tabla 54) · RF-DIS-01 a 03.

Guarda el estado de cada asiento *para cada evento* (RN22). El cambio de estado es atómico y de
todo o nada: un único UPDATE condicionado al estado esperado; si alguna fila no coincide se
revierte la transacción completa. Dos solicitudes simultáneas no pueden tomar el mismo asiento,
porque la segunda encuentra la fila ya bloqueada/cambiada por la primera (RN15).
"""
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Enum, Index, Integer, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from common.app import crear_app
from common.auth import requiere
from common.clients import asientos, eventos, ids_param, localidades, parse_ids
from common.security import exigir_clave_interna

from .database import Base, engine, get_db, preparar

Estado = Literal["disponible", "reservado", "vendido"]


class DisponibilidadAsiento(Base):
    __tablename__ = "disponibilidad_asiento"
    __table_args__ = (Index("ix_disp_evento_estado", "id_evento", "estado"),)

    id_evento: Mapped[int] = mapped_column(Integer, primary_key=True)    # RL -> Eventos
    id_asiento: Mapped[int] = mapped_column(Integer, primary_key=True)   # RL -> Asientos
    estado: Mapped[str] = mapped_column(
        Enum("disponible", "reservado", "vendido", name="estado_disponibilidad"),
        nullable=False, default="disponible", server_default="disponible")


class PublicarIn(BaseModel):
    id_evento: int
    id_escenario: int


class SincronizarIn(BaseModel):
    id_escenario: int


class CambiarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_evento: int
    asientos: list[int] = Field(min_length=1, max_length=200)
    desde: Estado
    hacia: Estado


router = APIRouter()


def _asientos_del_escenario(id_escenario: int) -> tuple[list[dict], list[dict]]:
    locs = localidades.get("/internal/localidades", escenarios=str(id_escenario))
    if not locs:
        return [], []
    sillas = asientos.get("/internal/asientos", localidades=ids_param(l["id_localidad"] for l in locs))
    return locs, sillas


def publicar(db: Session, id_evento: int, id_escenario: int) -> dict:
    _, sillas = _asientos_del_escenario(id_escenario)
    existentes = set(db.scalars(select(DisponibilidadAsiento.id_asiento)
                                .where(DisponibilidadAsiento.id_evento == id_evento)))
    nuevos = [s["id_asiento"] for s in sillas if s["id_asiento"] not in existentes]
    db.add_all(DisponibilidadAsiento(id_evento=id_evento, id_asiento=i, estado="disponible") for i in nuevos)
    db.commit()
    return {"id_evento": id_evento, "publicados": len(nuevos), "total": len(existentes) + len(nuevos)}


# ---------------- Consulta ----------------
@router.get("/disponibilidad/eventos/{id_evento}", tags=["Disponibilidad"],
            summary="RF-DIS-02 Mapa de asientos por localidad con precio y conteo por estado")
def por_evento(id_evento: int, _: dict = Depends(requiere("consultar_eventos")),
               db: Session = Depends(get_db)):
    ev = eventos.get(f"/internal/eventos/{id_evento}")
    locs, sillas = _asientos_del_escenario(ev["id_escenario"])
    estados = dict(db.execute(select(DisponibilidadAsiento.id_asiento, DisponibilidadAsiento.estado)
                              .where(DisponibilidadAsiento.id_evento == id_evento)).all())
    por_loc: dict[int, list] = defaultdict(list)
    for s in sillas:
        if s["id_asiento"] in estados:  # solo asientos publicados para este evento
            por_loc[s["id_localidad"]].append({"id_asiento": s["id_asiento"], "fila": s["fila"],
                                               "numero": s["numero"], "estado": estados[s["id_asiento"]]})
    salida, totales = [], {"disponible": 0, "reservado": 0, "vendido": 0}
    for l in locs:
        lista = por_loc.get(l["id_localidad"], [])
        conteo = {"disponible": 0, "reservado": 0, "vendido": 0}
        for a in lista:
            conteo[a["estado"]] += 1
            totales[a["estado"]] += 1
        salida.append({**l, "conteo": conteo, "asientos": lista})
    return {"id_evento": id_evento, "estado_evento": ev["estado"], "localidades": salida,
            "totales": {**totales, "total": sum(totales.values())}}


@router.get("/disponibilidad/resumen", tags=["Disponibilidad"],
            summary="Conteo por estado y precio desde, para varios eventos (catálogo)")
def resumen(eventos_ids: str = "", _: dict = Depends(requiere("consultar_eventos")),
            db: Session = Depends(get_db)):
    ids = parse_ids(eventos_ids)
    if not ids:
        return []
    filas = db.execute(select(DisponibilidadAsiento.id_evento, DisponibilidadAsiento.estado, func.count())
                       .where(DisponibilidadAsiento.id_evento.in_(ids))
                       .group_by(DisponibilidadAsiento.id_evento, DisponibilidadAsiento.estado)).all()
    conteos: dict[int, dict] = {i: {"disponible": 0, "reservado": 0, "vendido": 0} for i in ids}
    for ide, est, n in filas:
        conteos[ide][est] = n
    evs = eventos.get("/internal/eventos", ids=ids_param(ids))
    esc_de = {e["id_evento"]: e["id_escenario"] for e in evs}
    precios: dict[int, list[float]] = defaultdict(list)
    if esc_de:
        for l in localidades.get("/internal/localidades", escenarios=ids_param(set(esc_de.values()))):
            precios[l["id_escenario"]].append(float(l["precio"]))
    salida = []
    for i in ids:
        c = conteos[i]
        p = precios.get(esc_de.get(i), [])
        salida.append({"id_evento": i, **c, "total": sum(c.values()),
                       "precio_desde": min(p) if p else None, "precio_hasta": max(p) if p else None})
    return salida


# ---------------- Internas ----------------
@router.post("/internal/disponibilidad/publicar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_publicar(datos: PublicarIn, db: Session = Depends(get_db)):
    return publicar(db, datos.id_evento, datos.id_escenario)


@router.post("/internal/disponibilidad/sincronizar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_sincronizar(datos: SincronizarIn, db: Session = Depends(get_db)):
    total = 0
    for ev in eventos.get("/internal/eventos", id_escenario=datos.id_escenario, estado="en_venta"):
        total += publicar(db, ev["id_evento"], datos.id_escenario)["publicados"]
    return {"publicados": total}


@router.post("/internal/disponibilidad/cambiar", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_cambiar(datos: CambiarIn, db: Session = Depends(get_db)):
    """RF-DIS-03: cambio atómico de estado, todo o nada."""
    if datos.desde == datos.hacia:
        raise HTTPException(422, "El estado de origen y destino deben ser distintos")
    ids = sorted(set(datos.asientos))
    try:
        res = db.execute(update(DisponibilidadAsiento)
                         .where(DisponibilidadAsiento.id_evento == datos.id_evento,
                                DisponibilidadAsiento.id_asiento.in_(ids),
                                DisponibilidadAsiento.estado == datos.desde)
                         .values(estado=datos.hacia))
        if res.rowcount != len(ids):
            db.rollback()
            actuales = dict(db.execute(
                select(DisponibilidadAsiento.id_asiento, DisponibilidadAsiento.estado)
                .where(DisponibilidadAsiento.id_evento == datos.id_evento,
                       DisponibilidadAsiento.id_asiento.in_(ids))).all())
            conflicto = [i for i in ids if actuales.get(i) != datos.desde]
            raise HTTPException(409, {
                "mensaje": "Algunos asientos ya no están disponibles" if datos.desde == "disponible"
                else f"Algunos asientos no están en estado {datos.desde}",
                "asientos": conflicto})
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    return {"id_evento": datos.id_evento, "asientos": ids, "estado": datos.hacia}


@router.post("/internal/disponibilidad/liberar-evento/{id_evento}", include_in_schema=False,
             dependencies=[Depends(exigir_clave_interna)])
def interno_liberar_evento(id_evento: int, db: Session = Depends(get_db)):
    """Evento cancelado: sus boletas se reembolsaron en créditos, así que todos los asientos vuelven a
    estar disponibles por si el evento se reactiva."""
    res = db.execute(update(DisponibilidadAsiento)
                     .where(DisponibilidadAsiento.id_evento == id_evento,
                            DisponibilidadAsiento.estado != "disponible")
                     .values(estado="disponible"))
    db.commit()
    return {"liberados": res.rowcount}


app = crear_app("disponibilidad", "Microservicio de Disponibilidad",
                "Estado de cada asiento por evento; garantiza que no se asigne dos veces (RF-DIS-01 a 03).",
                router, Base, engine, preparar)
