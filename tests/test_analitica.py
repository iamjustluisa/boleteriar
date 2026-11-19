"""Sprints 7 y 8: ETL hacia el Data Warehouse e indicadores del dashboard."""
import httpx
import pytest

from .conftest import auth, nuevo_usuario
from .test_estados_creditos import RECHAZO, TARJETA, admin, comprar, libres, montar, u  # noqa: F401


def etl(h):
    r = httpx.post(u("analitica", "/analitica/etl"), headers=h, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def test_usuario_normal_no_ve_indicadores():
    _, tok, _ = nuevo_usuario("ana")
    assert httpx.get(u("analitica", "/analitica/indicadores"), headers=auth(tok)).status_code == 403
    assert httpx.post(u("analitica", "/analitica/etl"), headers=auth(tok)).status_code == 403


def test_etl_cuadra_con_el_origen_e_indicadores(admin):  # noqa: F811
    loc, ev = montar(admin, precio=100000, asientos=6)
    _, tok, _ = nuevo_usuario("dw")
    h = auth(tok)
    sillas = libres(h, ev["id_evento"])
    assert comprar(h, ev["id_evento"], sillas[:2], **TARJETA).status_code == 201      # 2 boletas
    assert comprar(h, ev["id_evento"], sillas[2:3], **RECHAZO).status_code in (201, 402)  # rechazado

    r = etl(admin)
    assert r["estado"] == "ok", r
    assert r["calidad"]["cuadra"] is True
    assert r["calidad"]["boletas_origen"] == r["calidad"]["boletas_dw"]

    ind = httpx.get(u("analitica", "/analitica/indicadores"), headers=admin).json()
    fila = next(e for e in ind["por_evento"] if e["evento"] == ev["nombre"])
    assert fila["boletas"] == 2 and fila["ingresos"] == 200000
    assert fila["asientos"] == 6 and fila["vendidos"] == 2 and fila["ocupacion"] == pytest.approx(33.3, abs=0.1)
    assert ind["kpi"]["boletas_vendidas"] >= 2 and ind["kpi"]["reservas"] >= 2
    assert ind["actualizado"] is not None
    assert any(m["metodo"] == "tarjeta" for m in ind["por_metodo"])

    # recarga completa: ejecutar dos veces no duplica hechos
    r2 = etl(admin)
    assert r2["filas"]["fact_venta"] == r["filas"]["fact_venta"]
    hist = httpx.get(u("analitica", "/analitica/etl/ejecuciones"), headers=admin).json()
    assert len(hist) >= 2 and hist[0]["estado"] == "ok"


def test_cancelacion_se_refleja_en_el_dw(admin):  # noqa: F811
    loc, ev = montar(admin, precio=50000, asientos=4)
    _, tok, _ = nuevo_usuario("dw")
    h = auth(tok)
    assert comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA).status_code == 201
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"}).raise_for_status()
    r = etl(admin)
    assert r["calidad"]["cuadra"]
    ind = httpx.get(u("analitica", "/analitica/indicadores"), headers=admin).json()
    fila = next(e for e in ind["por_evento"] if e["evento"] == ev["nombre"])
    assert fila["estado"] == "cancelado" and fila["boletas"] == 0
    assert ind["kpi"]["boletas_canceladas"] >= 1 and ind["kpi"]["creditos_abonados"] >= 50000
