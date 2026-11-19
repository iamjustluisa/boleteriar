"""Pruebas de punta a punta de los microservicios de catálogo, reservas, compras, pagos y boletas,
organizadas por requerimiento y regla del negocio."""
import concurrent.futures as cf
from datetime import date, timedelta

import httpx
import pytest

from .conftest import KEY, URL, auth, nuevo_admin, nuevo_usuario

TARJETA_OK = "4242 4242 4242 4242"
TARJETA_RECHAZO = "4000 0000 0000 0002"


def u(servicio, ruta):
    return f"{URL[servicio]}{ruta}"


@pytest.fixture(scope="module")
def admin():
    return auth(nuevo_admin()[0])


@pytest.fixture(scope="module")
def evento(admin):
    """Escenario con 2 localidades (2×5 y 2×5 asientos) y un evento programado."""
    esc = httpx.post(u("escenarios", "/escenarios"), headers=admin,
                     json={"nombre": "Arena Test", "direccion": "Calle 1", "capacidad": 50}).json()
    locs = []
    for nombre, precio in (("VIP", 200000), ("General", 80000)):
        loc = httpx.post(u("localidades", "/localidades"), headers=admin, json={
            "id_escenario": esc["id_escenario"], "nombre": nombre, "precio": precio, "capacidad": 10}).json()
        r = httpx.post(u("asientos", "/asientos/generar"), headers=admin,
                       json={"id_localidad": loc["id_localidad"], "filas": 2, "asientos_por_fila": 5})
        assert r.status_code == 200 and r.json()["creados"] == 10
        locs.append(loc)
    ev = httpx.post(u("eventos", "/eventos"), headers=admin, json={
        "id_escenario": esc["id_escenario"], "nombre": "Concierto de prueba",
        "fecha": (date.today() + timedelta(days=20)).isoformat(), "hora": "20:00"})
    assert ev.status_code == 201, ev.text
    ev = ev.json()
    assert ev["disponibilidad"]["publicados"] == 20          # RF-DIS-01
    return {"escenario": esc, "localidades": locs, "evento": ev}


def mapa(h, id_evento):
    return httpx.get(u("disponibilidad", f"/disponibilidad/eventos/{id_evento}"), headers=h).json()


def libres(h, id_evento, n, localidad=0):
    m = mapa(h, id_evento)
    return [a["id_asiento"] for a in m["localidades"][localidad]["asientos"] if a["estado"] == "disponible"][:n]


def reservar(h, id_evento, asientos):
    return httpx.post(u("reservas", "/reservas"), headers=h, json={"id_evento": id_evento, "asientos": asientos})


def comprar_y_pagar(h, id_reserva, tarjeta=TARJETA_OK):
    c = httpx.post(u("compras", "/compras"), headers=h, json={"id_reserva": id_reserva})
    assert c.status_code == 201, c.text
    p = httpx.post(u("pagos", "/pagos"), headers=h, json={
        "id_compra": c.json()["id_compra"], "titular": "Ana Pérez", "numero_tarjeta": tarjeta,
        "vencimiento": "12/30", "cvv": "123"})
    return c.json(), p


# ------------------------------------------------------------------ catálogo y permisos
def test_usuario_no_administra_catalogo(evento):
    _, t, _ = nuevo_usuario()
    r = httpx.post(u("escenarios", "/escenarios"), headers=auth(t),
                   json={"nombre": "X", "direccion": "Y", "capacidad": 5})
    assert r.status_code == 403                                  # RN20


def test_sin_sesion_no_hay_catalogo():
    assert httpx.get(u("eventos", "/eventos")).status_code == 401


def test_rutas_internas_exigen_clave():
    assert httpx.get(u("usuarios", "/internal/usuarios/1")).status_code == 403


def test_catalogo_lista_solo_programados_con_escenario(evento):
    _, t, _ = nuevo_usuario()
    evs = httpx.get(u("eventos", "/eventos"), headers=auth(t)).json()
    ev = next(e for e in evs if e["id_evento"] == evento["evento"]["id_evento"])
    assert ev["estado"] == "programado" and ev["escenario"]["nombre"] == "Arena Test"


def test_evento_requiere_escenario_existente(admin):
    r = httpx.post(u("eventos", "/eventos"), headers=admin, json={
        "id_escenario": 99999, "nombre": "X", "fecha": (date.today() + timedelta(days=5)).isoformat(), "hora": "20:00"})
    assert r.status_code == 404                                   # RF-EVE-01


def test_localidad_unica_y_capacidad(admin, evento):
    id_esc = evento["escenario"]["id_escenario"]
    dup = httpx.post(u("localidades", "/localidades"), headers=admin,
                     json={"id_escenario": id_esc, "nombre": "VIP", "precio": 1, "capacidad": 1})
    assert dup.status_code == 409                                  # RF-LOC-01 nombre único
    excede = httpx.post(u("localidades", "/localidades"), headers=admin,
                        json={"id_escenario": id_esc, "nombre": "Otra", "precio": 1, "capacidad": 31})
    assert excede.status_code == 409


def test_no_se_elimina_escenario_con_eventos(admin, evento):
    r = httpx.delete(u("escenarios", f"/escenarios/{evento['escenario']['id_escenario']}"), headers=admin)
    assert r.status_code == 409 and "evento" in r.json()["detail"]  # RF-ESC-03


def test_disponibilidad_por_localidad_con_precio(evento):
    _, t, _ = nuevo_usuario()
    m = mapa(auth(t), evento["evento"]["id_evento"])
    assert [l["nombre"] for l in m["localidades"]] == ["VIP", "General"]
    assert m["localidades"][0]["precio"] == 200000 and m["totales"]["total"] == 20   # RF-DIS-02


# ------------------------------------------------------------------ reservas
def test_reserva_todo_o_nada(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t1, _ = nuevo_usuario(); _, t2, _ = nuevo_usuario()
    a, b = libres(auth(t1), id_ev, 2, localidad=1)
    assert reservar(auth(t1), id_ev, [a]).status_code == 201
    r = reservar(auth(t2), id_ev, [a, b])
    assert r.status_code == 409 and r.json()["detail"]["asientos"] == [a]   # RF-RES-01
    estados = {x["id_asiento"]: x["estado"] for l in mapa(auth(t2), id_ev)["localidades"] for x in l["asientos"]}
    assert estados[b] == "disponible"                               # no se reservó ninguno


def test_concurrencia_un_solo_ganador(evento):
    id_ev = evento["evento"]["id_evento"]
    tokens = [auth(nuevo_usuario("conc")[1]) for _ in range(12)]
    objetivo = libres(tokens[0], id_ev, 2, localidad=1)
    with cf.ThreadPoolExecutor(12) as ex:
        codigos = list(ex.map(lambda h: reservar(h, id_ev, objetivo).status_code, tokens))
    assert codigos.count(201) == 1 and codigos.count(409) == 11      # RN15, RF-DIS-03


def test_cancelar_reserva_libera_asientos(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    asiento = libres(auth(t), id_ev, 1, localidad=1)
    r = reservar(auth(t), id_ev, asiento).json()
    c = httpx.put(u("reservas", f"/reservas/{r['id_reserva']}/cancelar"), headers=auth(t))
    assert c.status_code == 200 and c.json()["estado"] == "cancelada"   # RF-RES-03
    assert asiento[0] in libres(auth(t), id_ev, 50, localidad=1)


def test_no_se_ve_ni_cancela_reserva_ajena(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t1, _ = nuevo_usuario(); _, t2, _ = nuevo_usuario()
    r = reservar(auth(t1), id_ev, libres(auth(t1), id_ev, 1, localidad=1)).json()
    assert httpx.get(u("reservas", f"/reservas/{r['id_reserva']}"), headers=auth(t2)).status_code == 404
    assert httpx.put(u("reservas", f"/reservas/{r['id_reserva']}/cancelar"), headers=auth(t2)).status_code == 404


def test_reserva_vencida_expira_y_libera(evento):
    from reservas.database import SessionLocal
    from reservas.main import Reserva
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    asiento = libres(auth(t), id_ev, 1, localidad=1)
    r = reservar(auth(t), id_ev, asiento).json()
    with SessionLocal() as db:                                      # simula que pasó el tiempo límite
        db.get(Reserva, r["id_reserva"]).fecha_vencimiento -= timedelta(hours=1)
        db.commit()
    assert httpx.post(u("reservas", "/internal/reservas/expirar"), headers=KEY).json()["expiradas"] >= 1
    assert httpx.get(u("reservas", f"/reservas/{r['id_reserva']}"), headers=auth(t)).json()["estado"] == "expirada"
    assert asiento[0] in libres(auth(t), id_ev, 50, localidad=1)     # RF-RES-04, RN16


# ------------------------------------------------------------------ compras, pagos y boletas
def test_compra_pago_aprobado_emite_boletas(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    asientos = libres(auth(t), id_ev, 2, localidad=0)
    r = reservar(auth(t), id_ev, asientos).json()
    compra, p = comprar_y_pagar(auth(t), r["id_reserva"])
    assert compra["estado"] == "pendiente" and compra["valor_total"] == 400000      # RF-COM-02
    assert p.status_code == 201 and p.json()["estado"] == "aprobado"
    boletas = p.json()["boletas"]
    assert len(boletas) == 2 and len({b["codigo_boleta"] for b in boletas}) == 2     # RN18, RF-BOL-01
    assert sum(b["precio"] for b in boletas) == compra["valor_total"]
    estados = {x["id_asiento"]: x["estado"] for l in mapa(auth(t), id_ev)["localidades"] for x in l["asientos"]}
    assert all(estados[a] == "vendido" for a in asientos)                         # RN13
    assert httpx.get(u("compras", f"/compras/{compra['id_compra']}"), headers=auth(t)).json()["estado"] == "pagada"
    mis = httpx.get(u("boletas", "/boletas/mis"), headers=auth(t)).json()
    assert {b["id_asiento"] for b in mis} == set(asientos)                        # RF-BOL-02
    estado_pago = httpx.get(u("pagos", f"/pagos/compra/{compra['id_compra']}"), headers=auth(t)).json()
    assert estado_pago["estado"] == "aprobado"                                     # RF-PAG-02


def test_reserva_se_compra_una_sola_vez(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    r = reservar(auth(t), id_ev, libres(auth(t), id_ev, 1, localidad=1)).json()
    comprar_y_pagar(auth(t), r["id_reserva"])
    again = httpx.post(u("compras", "/compras"), headers=auth(t), json={"id_reserva": r["id_reserva"]})
    assert again.status_code == 409                                                 # RF-COM-01


def test_pago_rechazado_libera_y_no_emite(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    asiento = libres(auth(t), id_ev, 1, localidad=1)
    r = reservar(auth(t), id_ev, asiento).json()
    compra, p = comprar_y_pagar(auth(t), r["id_reserva"], TARJETA_RECHAZO)
    assert p.json()["estado"] == "rechazado" and p.json()["boletas"] == []          # RN17, RN18
    assert httpx.get(u("compras", f"/compras/{compra['id_compra']}"), headers=auth(t)).json()["estado"] == "rechazada"
    assert asiento[0] in libres(auth(t), id_ev, 50, localidad=1)


def test_tarjeta_invalida_no_registra_pago(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    r = reservar(auth(t), id_ev, libres(auth(t), id_ev, 1, localidad=1)).json()
    c = httpx.post(u("compras", "/compras"), headers=auth(t), json={"id_reserva": r["id_reserva"]}).json()
    p = httpx.post(u("pagos", "/pagos"), headers=auth(t), json={
        "id_compra": c["id_compra"], "titular": "Ana", "numero_tarjeta": "1234 5678 9012 3456",
        "vencimiento": "12/30", "cvv": "123"})
    assert p.status_code == 422
    assert httpx.get(u("pagos", f"/pagos/compra/{c['id_compra']}"), headers=auth(t)).status_code == 404


def test_no_se_paga_compra_ajena(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t1, _ = nuevo_usuario(); _, t2, _ = nuevo_usuario()
    r = reservar(auth(t1), id_ev, libres(auth(t1), id_ev, 1, localidad=1)).json()
    c = httpx.post(u("compras", "/compras"), headers=auth(t1), json={"id_reserva": r["id_reserva"]}).json()
    p = httpx.post(u("pagos", "/pagos"), headers=auth(t2), json={
        "id_compra": c["id_compra"], "titular": "Ana", "numero_tarjeta": TARJETA_OK, "vencimiento": "12/30", "cvv": "123"})
    assert p.status_code == 404                                                      # RNF02


def test_boleta_unica_por_asiento_y_evento(evento):
    _, t, _ = nuevo_usuario()
    id_ev = evento["evento"]["id_evento"]
    r = reservar(auth(t), id_ev, libres(auth(t), id_ev, 1, localidad=1)).json()
    _, p = comprar_y_pagar(auth(t), r["id_reserva"])
    vendido = p.json()["boletas"][0]["id_asiento"]
    dup = httpx.post(u("boletas", "/internal/boletas/generar"), headers=KEY, json={
        "id_compra": 999999, "id_evento": id_ev, "items": [{"id_asiento": vendido, "precio": 1}]})
    assert dup.status_code == 409                                                    # RF-BOL-03


def test_historial_incluye_reservas_y_compras(evento):
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    r = reservar(auth(t), id_ev, libres(auth(t), id_ev, 1, localidad=1)).json()
    comprar_y_pagar(auth(t), r["id_reserva"])
    h = httpx.get(u("compras", "/historial"), headers=auth(t)).json()
    assert h["resumen"]["compras_pagadas"] == 1 and h["reservas"][0]["compra"]["estado"] == "pagada"   # RF-COM-03


def test_notificaciones_de_reserva_y_pago(evento):
    import time
    id_ev = evento["evento"]["id_evento"]
    _, t, _ = nuevo_usuario()
    r = reservar(auth(t), id_ev, libres(auth(t), id_ev, 1, localidad=1)).json()
    comprar_y_pagar(auth(t), r["id_reserva"])
    for _ in range(40):
        n = httpx.get(u("notificaciones", "/notificaciones/mis"), headers=auth(t)).json()
        if n["pendientes"] >= 2:
            break
        time.sleep(0.1)
    assert {x["tipo"] for x in n["items"]} == {"reserva", "pago"}                   # RF-NOT-01, 02
    httpx.post(u("notificaciones", "/notificaciones/marcar-enviadas"), headers=auth(t))
    n = httpx.get(u("notificaciones", "/notificaciones/mis"), headers=auth(t)).json()
    assert n["pendientes"] == 0 and all(x["fecha_envio"] for x in n["items"])


def test_auditoria_registra_y_solo_admin_consulta(admin, evento):
    import time
    from common.auditoria import esperar_pendientes
    esperar_pendientes()
    time.sleep(0.5)
    _, t, _ = nuevo_usuario()
    assert httpx.get(u("auditoria", "/auditoria"), headers=auth(t)).status_code == 403          # RN20
    acciones = httpx.get(u("auditoria", "/auditoria/acciones"), headers=admin).json()
    for a in ("REGISTRO_USUARIO", "LOGIN_OK", "RESERVA_CREADA", "COMPRA_REGISTRADA", "PAGO_APROBADO", "BOLETA_EMITIDA"):
        assert a in acciones                                                                 # RF-AUD-01
    filtrado = httpx.get(u("auditoria", "/auditoria?accion=PAGO_APROBADO"), headers=admin).json()
    assert filtrado["total"] >= 1 and all(i["accion"] == "PAGO_APROBADO" for i in filtrado["items"])  # RF-AUD-03
    metodos = {m for r in __import__("auditoria.main").main.app.routes for m in getattr(r, "methods", set())}
    assert "DELETE" not in metodos and "PUT" not in metodos                                    # RF-AUD-02


def test_cancelar_evento_impide_reservas_y_anula_boletas(admin):
    esc = httpx.post(u("escenarios", "/escenarios"), headers=admin,
                     json={"nombre": "Sala C", "direccion": "Calle 9", "capacidad": 10}).json()
    loc = httpx.post(u("localidades", "/localidades"), headers=admin, json={
        "id_escenario": esc["id_escenario"], "nombre": "Única", "precio": 1000, "capacidad": 4}).json()
    httpx.post(u("asientos", "/asientos/generar"), headers=admin, json={"id_localidad": loc["id_localidad"], "filas": 1, "asientos_por_fila": 4})
    ev = httpx.post(u("eventos", "/eventos"), headers=admin, json={
        "id_escenario": esc["id_escenario"], "nombre": "Obra de teatro",
        "fecha": (date.today() + timedelta(days=9)).isoformat(), "hora": "18:00"}).json()
    _, t, _ = nuevo_usuario()
    a = libres(auth(t), ev["id_evento"], 3)
    pagada = reservar(auth(t), ev["id_evento"], a[:1]).json()
    comprar_y_pagar(auth(t), pagada["id_reserva"])
    activa = reservar(auth(t), ev["id_evento"], a[1:2]).json()
    r = httpx.put(u("eventos", f"/eventos/{ev['id_evento']}/estado"), headers=admin, json={"estado": "cancelado"}).json()
    assert r["reservas_canceladas"] == 1 and r["boletas_canceladas"] == 1                   # RF-EVE-02
    assert reservar(auth(t), ev["id_evento"], a[2:3]).status_code == 409
    assert httpx.get(u("reservas", f"/reservas/{activa['id_reserva']}"), headers=auth(t)).json()["estado"] == "cancelada"
    h = httpx.get(u("compras", "/historial"), headers=auth(t)).json()
    assert len(h["reservas"]) == 2                                                          # RN14: se conserva
