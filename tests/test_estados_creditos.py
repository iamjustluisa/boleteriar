"""Estados del evento (aplazado, cancelado → créditos → reactivado, realizado automático), pago con
créditos, Precio Justo Garantizado e imagen del evento."""
import base64
import time
from datetime import date, timedelta

import httpx
import pytest

from .conftest import URL, auth, nuevo_admin, nuevo_usuario

TARJETA = {"titular": "Ana Pérez", "numero_tarjeta": "4242 4242 4242 4242", "vencimiento": "12/30", "cvv": "123"}
RECHAZO = {**TARJETA, "numero_tarjeta": "4000 0000 0000 0002"}
_n = {"i": 0}


def u(s, r):
    return f"{URL[s]}{r}"


@pytest.fixture(scope="module")
def admin():
    return auth(nuevo_admin()[0])


def montar(admin, precio=200000, asientos=6, dias=30):
    """Escenario propio con una localidad y un evento programado."""
    _n["i"] += 1
    esc = httpx.post(u("escenarios", "/escenarios"), headers=admin,
                     json={"nombre": f"Sala {_n['i']}", "direccion": "Calle 5", "capacidad": 100}).json()
    loc = httpx.post(u("localidades", "/localidades"), headers=admin, json={
        "id_escenario": esc["id_escenario"], "nombre": "VIP", "precio": precio, "capacidad": asientos}).json()
    httpx.post(u("asientos", "/asientos/generar"), headers=admin,
               json={"id_localidad": loc["id_localidad"], "filas": 1, "asientos_por_fila": asientos})
    ev = httpx.post(u("eventos", "/eventos"), headers=admin, json={
        "id_escenario": esc["id_escenario"], "nombre": f"Concierto {_n['i']}",
        "fecha": (date.today() + timedelta(days=dias)).isoformat(), "hora": "20:00"}).json()
    return loc, ev


def libres(h, id_evento):
    m = httpx.get(u("disponibilidad", f"/disponibilidad/eventos/{id_evento}"), headers=h).json()
    return [a["id_asiento"] for l in m["localidades"] for a in l["asientos"] if a["estado"] == "disponible"]


def comprar(h, id_evento, asientos, **pago):
    r = httpx.post(u("reservas", "/reservas"), headers=h, json={"id_evento": id_evento, "asientos": asientos})
    assert r.status_code == 201, r.text
    c = httpx.post(u("compras", "/compras"), headers=h, json={"id_reserva": r.json()["id_reserva"]}).json()
    return httpx.post(u("pagos", "/pagos"), headers=h, json={"id_compra": c["id_compra"], **pago})


def saldo(h):
    return httpx.get(u("pagos", "/creditos/mis"), headers=h).json()["saldo"]


def esperar_notif(h, tipo, intentos=40):
    for _ in range(intentos):
        items = httpx.get(u("notificaciones", "/notificaciones/mis"), headers=h).json()["items"]
        if any(n["tipo"] == tipo for n in items):
            return True
        time.sleep(0.1)
    return False


# ------------------------------------------------------------------ aplazado
def test_cambiar_fecha_deja_aplazado_y_sigue_a_la_venta(admin):
    _, ev = montar(admin)
    _, t, _ = nuevo_usuario(); h = auth(t)
    assert comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA).json()["estado"] == "aprobado"
    nueva = (date.today() + timedelta(days=45)).isoformat()
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin,
                  json={"nombre": ev["nombre"], "fecha": nueva, "hora": "21:00"}).json()
    assert r["estado"] == "aplazado" and r["cambio"] == "aplazado" and r["notificados"] == 1
    assert esperar_notif(h, "evento")                                    # aviso a quien ya compró
    catalogo = httpx.get(u("eventos", "/eventos"), headers=h).json()
    assert any(e["id_evento"] == ev["id_evento"] and e["estado"] == "aplazado" for e in catalogo)
    assert comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA).json()["estado"] == "aprobado"


def test_editar_sin_cambiar_fecha_no_aplaza(admin):
    _, ev = montar(admin)
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin,
                  json={"nombre": "Nombre nuevo", "fecha": ev["fecha"], "hora": ev["hora"][:5]}).json()
    assert r["estado"] == "programado" and r["cambio"] is None


# ------------------------------------------------------------------ cancelado → créditos → reactivado
def test_cancelar_devuelve_creditos_y_reactivar_permite_revender(admin):
    _, ev = montar(admin, precio=150000)
    _, t, _ = nuevo_usuario(); h = auth(t)
    asientos = libres(h, ev["id_evento"])[:2]
    assert comprar(h, ev["id_evento"], asientos, **TARJETA).status_code == 201
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"}).json()
    assert r["boletas_canceladas"] == 2 and r["creditos_devueltos"] == 300000
    assert saldo(h) == 300000
    assert esperar_notif(h, "credito")
    assert set(asientos) <= set(libres(h, ev["id_evento"]))                 # asientos liberados
    assert all(b["estado"] == "cancelada" for b in httpx.get(u("boletas", "/boletas/mis"), headers=h).json())
    # no se puede reservar un evento cancelado
    assert httpx.post(u("reservas", "/reservas"), headers=h,
                      json={"id_evento": ev["id_evento"], "asientos": asientos[:1]}).status_code == 409
    # reactivar editándolo (misma fecha) → programado
    re_ = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin,
                    json={"nombre": ev["nombre"], "fecha": ev["fecha"], "hora": ev["hora"][:5]}).json()
    assert re_["estado"] == "programado" and re_["cambio"] == "reactivado"
    # el mismo asiento se vuelve a vender (unicidad solo entre boletas vigentes), pagando con créditos
    p = comprar(h, ev["id_evento"], asientos, usar_creditos=True).json()
    assert p["estado"] == "aprobado" and p["metodo"] == "creditos" and p["valor_creditos"] == 300000
    assert saldo(h) == 0 and len(p["boletas"]) == 2
    # un segundo reembolso del mismo evento no duplica créditos
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"})
    assert saldo(h) == 300000


def test_reactivar_con_otra_fecha_queda_aplazado(admin):
    _, ev = montar(admin)
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"})
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin, json={
        "nombre": ev["nombre"], "fecha": (date.today() + timedelta(days=60)).isoformat(), "hora": "19:00"}).json()
    assert r["estado"] == "aplazado" and r["cambio"] == "reactivado"


def test_evento_realizado_no_se_edita_ni_cancela(admin):
    _, ev = montar(admin)
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "realizado"})
    assert httpx.put(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin, json={
        "nombre": "x", "fecha": ev["fecha"], "hora": "20:00"}).status_code == 409
    assert httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin,
                     json={"estado": "cancelado"}).status_code == 409


def test_evento_con_fecha_pasada_queda_realizado(admin):
    from eventos.database import SessionLocal
    from eventos.main import Evento
    _, ev = montar(admin)
    with SessionLocal() as db:
        db.get(Evento, ev["id_evento"]).fecha = date.today() - timedelta(days=1)
        db.commit()
    r = httpx.get(u("eventos", f"/eventos/{ev['id_evento']}"), headers=admin).json()
    assert r["estado"] == "realizado"


# ------------------------------------------------------------------ pago con créditos
def test_pago_mixto_y_rechazo_no_consume_creditos(admin):
    _, ev = montar(admin, precio=100000)
    _, t, _ = nuevo_usuario(); h = auth(t)
    comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA)
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"})
    assert saldo(h) == 100000
    _, ev2 = montar(admin, precio=160000)
    # sin datos de tarjeta y sin saldo suficiente → error claro, sin cobrar
    r = httpx.post(u("reservas", "/reservas"), headers=h, json={"id_evento": ev2["id_evento"], "asientos": libres(h, ev2["id_evento"])[:1]}).json()
    c = httpx.post(u("compras", "/compras"), headers=h, json={"id_reserva": r["id_reserva"]}).json()
    falta = httpx.post(u("pagos", "/pagos"), headers=h, json={"id_compra": c["id_compra"], "usar_creditos": True})
    assert falta.status_code == 422 and saldo(h) == 100000
    # tarjeta rechazada en pago mixto: los créditos no se tocan
    rech = httpx.post(u("pagos", "/pagos"), headers=h, json={"id_compra": c["id_compra"], "usar_creditos": True, **RECHAZO}).json()
    assert rech["estado"] == "rechazado" and saldo(h) == 100000
    # pago mixto aprobado: 100.000 en créditos + 60.000 con tarjeta
    p = comprar(h, ev2["id_evento"], libres(h, ev2["id_evento"])[:1], usar_creditos=True, **TARJETA).json()
    assert p["metodo"] == "mixto" and p["valor_creditos"] == 100000 and p["valor"] == 160000
    assert saldo(h) == 0
    movs = httpx.get(u("pagos", "/creditos/mis"), headers=h).json()["movimientos"]
    assert [m["tipo"] for m in movs][:2] == ["uso", "abono"]


# ------------------------------------------------------------------ Precio Justo Garantizado
def test_precio_justo_devuelve_la_diferencia_sin_duplicar(admin):
    loc, ev = montar(admin, precio=200000)
    _, t, _ = nuevo_usuario(); h = auth(t)
    comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA)
    cambiar = lambda precio: httpx.put(u("localidades", f"/localidades/{loc['id_localidad']}"), headers=admin,
                                       json={"nombre": "VIP", "precio": precio, "capacidad": loc["capacidad"]}).json()
    r = cambiar(150000)
    assert r["precio_justo"]["boletas"] == 1 and r["precio_justo"]["total"] == 50000
    assert saldo(h) == 50000
    cambiar(120000)
    assert saldo(h) == 80000                       # solo la nueva diferencia (30.000)
    cambiar(300000)
    assert saldo(h) == 80000                       # subir el precio no cobra ni devuelve
    cambiar(250000)
    assert saldo(h) == 80000                       # sigue por encima del mínimo ya compensado
    httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"})
    assert saldo(h) == 200000                      # al cancelar se completa lo pagado, nunca más
    assert esperar_notif(h, "credito")


def test_precio_justo_no_aplica_a_quien_compro_barato(admin):
    loc, ev = montar(admin, precio=100000)
    _, t, _ = nuevo_usuario(); h = auth(t)
    httpx.put(u("localidades", f"/localidades/{loc['id_localidad']}"), headers=admin,
              json={"nombre": "VIP", "precio": 80000, "capacidad": loc["capacidad"]})
    comprar(h, ev["id_evento"], libres(h, ev["id_evento"])[:1], **TARJETA)   # compró a 80.000
    httpx.put(u("localidades", f"/localidades/{loc['id_localidad']}"), headers=admin,
              json={"nombre": "VIP", "precio": 90000, "capacidad": loc["capacidad"]})
    assert saldo(h) == 0


# ------------------------------------------------------------------ imagen del evento
PNG_1PX = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


def test_subir_y_ver_imagen_del_evento(admin):
    _, ev = montar(admin)
    _, t, _ = nuevo_usuario()
    assert httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/imagen"), headers=auth(t),
                     json={"imagen": PNG_1PX}).status_code == 403
    assert httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/imagen"), headers=admin,
                     json={"imagen": "data:text/plain;base64,aG9sYQ=="}).status_code == 422
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/imagen"), headers=admin, json={"imagen": PNG_1PX})
    assert r.status_code == 200 and "/imagen?v=" in r.json()["imagen"]
    img = httpx.get(u("eventos", f"/eventos/{ev['id_evento']}/imagen"))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
    detalle = httpx.get(u("eventos", f"/eventos/{ev['id_evento']}"), headers=auth(t)).json()
    assert detalle["imagen"]
    assert httpx.delete(u("eventos", f"/eventos/{ev['id_evento']}/imagen"), headers=admin).status_code == 204
    assert httpx.get(u("eventos", f"/eventos/{ev['id_evento']}"), headers=auth(t)).json()["imagen"] is None
