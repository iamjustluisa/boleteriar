"""Datos de demostración. Usa las APIs reales de los microservicios (no escribe en la BD directo),
así que también sirve como prueba de punta a punta del flujo reserva → compra → pago → boleta.

Es idempotente: si ya hay escenarios no vuelve a crear el catálogo.

Uso:  python -m scripts.seed           (con los servicios corriendo)
"""
import os
import random
import sys
import time
from datetime import timedelta

import httpx

from common.app import hoy_local
from common.config import SERVICIOS, settings

KEY = {"X-Internal-Key": settings.internal_key}
TARJETA_OK = "4242 4242 4242 4242"

ADMIN = {"nombre": os.getenv("ADMIN_NOMBRE", "Admin"), "apellido": os.getenv("ADMIN_APELLIDO", "Boletería"),
         "correo": os.getenv("ADMIN_CORREO", "admin@boleteria.com"),
         "telefono": os.getenv("ADMIN_TELEFONO", "3000000000"),
         "documento": os.getenv("ADMIN_DOCUMENTO", "1000000000"),
         "contrasena": os.getenv("ADMIN_CONTRASENA", "Admin12345")}
DEMO = {"nombre": "Sofía", "apellido": "Ramírez (demo)", "correo": "usuario@boleteria.com",
        "telefono": "3011234567", "documento": "1000000001", "contrasena": "Usuario12345"}
PUBLICO = [
    {"nombre": "Laura", "apellido": "Martínez", "correo": "laura@demo.com", "telefono": "3109876543",
     "documento": "1000000002", "contrasena": "Demo12345"},
    {"nombre": "Andrés", "apellido": "Gómez", "correo": "andres@demo.com", "telefono": "3205551234",
     "documento": "1000000003", "contrasena": "Demo12345"},
    {"nombre": "Camila", "apellido": "Rojas", "correo": "camila@demo.com", "telefono": "3157778899",
     "documento": "1000000004", "contrasena": "Demo12345"},
]

ESCENARIOS = [
    {"nombre": "Arena Andina", "direccion": "Av. Calle 80 # 69-70, Bogotá", "capacidad": 300,
     "localidades": [("VIP", 480000, 2, 12), ("Platea", 280000, 5, 16), ("General", 150000, 6, 20)]},
    {"nombre": "Teatro Aurora", "direccion": "Cra. 7 # 22-47, Bogotá", "capacidad": 200,
     "localidades": [("Palco", 220000, 2, 8), ("Platea baja", 160000, 6, 14), ("Balcón", 90000, 4, 14)]},
    {"nombre": "Coliseo del Norte", "direccion": "Autopista Norte # 170-20, Bogotá", "capacidad": 260,
     "localidades": [("Preferencial", 250000, 3, 14), ("Oriental", 120000, 5, 18), ("Occidental", 120000, 5, 18)]},
]

# (nombre, escenario, días desde hoy, hora, descripción)
EVENTOS = [
    ("Noche de Cumbia Eléctrica", "Arena Andina", 6, "20:00",
     "Los Tambores del Magdalena mezclan gaita, tambor alegre y sintetizadores en un show de luces "
     "de dos horas. Concierto · Cumbia · Todas las edades."),
    ("Volcán Rojo · Gira Ceniza", "Coliseo del Norte", 11, "21:00",
     "La banda de rock bogotana presenta su tercer álbum con invitados sorpresa. Concierto · Rock · +16."),
    ("Sinfonía de los Andes", "Teatro Aurora", 15, "19:30",
     "Orquesta Filarmónica Juvenil con obras de compositores latinoamericanos. Música clásica."),
    ("Pulso: Festival Electrónico", "Arena Andina", 22, "22:00",
     "Seis horas de DJ sets, visuales en 360° y la mejor electrónica de la ciudad. Electrónica · +18."),
    ("Salsa Brava All Stars", "Coliseo del Norte", 29, "20:30",
     "Una orquesta de catorce músicos y los clásicos de la salsa caleña y neoyorquina. Concierto · Salsa."),
    ("Risas a Medianoche", "Teatro Aurora", 34, "22:30",
     "Cuatro comediantes, un micrófono y cero filtros. Stand-up comedy · +18."),
    ("Jazz al Atardecer", "Teatro Aurora", 41, "18:00",
     "Cuarteto de jazz con repertorio de standards y composiciones propias. Jazz · Todas las edades."),
    ("Vallenato de Patio", "Arena Andina", 55, "19:00",
     "Acordeón, caja y guacharaca: una parranda vallenata con artistas invitados. Concierto · Vallenato."),
]


def url(servicio: str, ruta: str) -> str:
    return f"{settings.url(servicio)}{ruta}"


def esperar_servicios(timeout: float = 240) -> None:
    fin = time.time() + timeout
    pendientes = set(SERVICIOS)
    while pendientes and time.time() < fin:
        for s in list(pendientes):
            try:
                if httpx.get(url(s, "/health"), timeout=3).status_code == 200:
                    pendientes.discard(s)
            except httpx.HTTPError:
                pass
        if pendientes:
            time.sleep(2)
    if pendientes:
        raise RuntimeError(f"Servicios sin responder: {sorted(pendientes)}")


def registrar(datos: dict) -> int:
    r = httpx.post(url("usuarios", "/usuarios/registro"), json=datos, timeout=30)
    if r.status_code == 201:
        return r.json()["id_usuario"]
    q = httpx.get(url("usuarios", "/internal/usuarios/por-correo"), params={"correo": datos["correo"]},
                  headers=KEY, timeout=30)
    q.raise_for_status()
    return q.json()["id_usuario"]


def login(correo: str, contrasena: str) -> dict:
    r = httpx.post(url("acceso", "/auth/login"), json={"correo": correo, "contrasena": contrasena}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ok(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url} → {r.status_code}: {r.text}")
    return r.json() if r.content else {}


def comprar(h: dict, id_evento: int, asientos: list[int]) -> dict | None:
    r = httpx.post(url("reservas", "/reservas"), json={"id_evento": id_evento, "asientos": asientos},
                   headers=h, timeout=30)
    if r.status_code != 201:
        return None
    reserva = r.json()
    compra = ok(httpx.post(url("compras", "/compras"), json={"id_reserva": reserva["id_reserva"]},
                           headers=h, timeout=30))
    return ok(httpx.post(url("pagos", "/pagos"), headers=h, timeout=60, json={
        "id_compra": compra["id_compra"], "titular": "Cliente Demo", "numero_tarjeta": TARJETA_OK,
        "vencimiento": "12/30", "cvv": "123"}))


def main() -> int:
    print("Esperando a los microservicios...")
    esperar_servicios()
    id_admin = registrar(ADMIN)
    httpx.put(url("acceso", f"/internal/credenciales/{id_admin}/rol"), json={"rol": "administrador"},
              headers=KEY, timeout=30).raise_for_status()
    registrar(DEMO)
    for p in PUBLICO:
        registrar(p)
    print(f"Cuentas listas: {ADMIN['correo']} (administrador) y {DEMO['correo']} (usuario)")

    h = login(ADMIN["correo"], ADMIN["contrasena"])
    if ok(httpx.get(url("escenarios", "/escenarios"), headers=h, timeout=30)) and \
            os.getenv("SEED_FORZAR", "false") != "true":
        print("El catálogo ya tiene datos; no se vuelve a sembrar.")
        return 0

    ids_esc, locs_esc = {}, {}
    for e in ESCENARIOS:
        esc = ok(httpx.post(url("escenarios", "/escenarios"), headers=h, timeout=30, json={
            "nombre": e["nombre"], "direccion": e["direccion"], "capacidad": e["capacidad"]}))
        ids_esc[e["nombre"]] = esc["id_escenario"]
        for nombre, precio, filas, por_fila in e["localidades"]:
            loc = ok(httpx.post(url("localidades", "/localidades"), headers=h, timeout=30, json={
                "id_escenario": esc["id_escenario"], "nombre": nombre, "precio": precio,
                "capacidad": filas * por_fila}))
            ok(httpx.post(url("asientos", "/asientos/generar"), headers=h, timeout=60, json={
                "id_localidad": loc["id_localidad"], "filas": filas, "asientos_por_fila": por_fila}))
            locs_esc.setdefault(esc["id_escenario"], []).append(loc["id_localidad"])
    print(f"{len(ids_esc)} escenarios con localidades y asientos creados")

    hoy = hoy_local()
    ids_ev = []
    for nombre, esc, dias, hora, desc in EVENTOS:
        ev = ok(httpx.post(url("eventos", "/eventos"), headers=h, timeout=60, json={
            "id_escenario": ids_esc[esc], "nombre": nombre, "descripcion": desc,
            "fecha": (hoy + timedelta(days=dias)).isoformat(), "hora": hora}))
        ids_ev.append(ev["id_evento"])
    print(f"{len(ids_ev)} eventos programados con su disponibilidad publicada")

    # Ventas de ejemplo para que el mapa de asientos se vea realista
    rnd = random.Random(2026)
    compradores = [login(p["correo"], p["contrasena"]) for p in PUBLICO]
    ventas = 0
    for id_evento in ids_ev:
        mapa = ok(httpx.get(url("disponibilidad", f"/disponibilidad/eventos/{id_evento}"), headers=h, timeout=60))
        for _ in range(rnd.randint(3, 6)):
            loc = rnd.choice(mapa["localidades"])
            libres = [a for a in loc["asientos"] if a["estado"] == "disponible"]
            if len(libres) < 6:
                continue
            ini = rnd.randrange(0, len(libres) - 5)
            elegidos = [a["id_asiento"] for a in libres[ini:ini + rnd.randint(2, 6)]]
            for a in loc["asientos"]:
                if a["id_asiento"] in elegidos:
                    a["estado"] = "vendido"
            if comprar(rnd.choice(compradores), id_evento, elegidos):
                ventas += 1

    # Una compra y una reserva cancelada para el usuario demo (historial y boletas con QR)
    hd = login(DEMO["correo"], DEMO["contrasena"])
    mapa = ok(httpx.get(url("disponibilidad", f"/disponibilidad/eventos/{ids_ev[0]}"), headers=hd, timeout=60))
    vip = [a["id_asiento"] for a in mapa["localidades"][0]["asientos"] if a["estado"] == "disponible"][:2]
    comprar(hd, ids_ev[0], vip)
    mapa = ok(httpx.get(url("disponibilidad", f"/disponibilidad/eventos/{ids_ev[2]}"), headers=hd, timeout=60))
    libre = [a["id_asiento"] for a in mapa["localidades"][-1]["asientos"] if a["estado"] == "disponible"][:1]
    r = httpx.post(url("reservas", "/reservas"), json={"id_evento": ids_ev[2], "asientos": libre}, headers=hd, timeout=30)
    if r.status_code == 201:
        httpx.put(url("reservas", f"/reservas/{r.json()['id_reserva']}/cancelar"), headers=hd, timeout=30)
    print(f"{ventas + 1} compras de ejemplo registradas. ¡Datos de demostración listos!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
