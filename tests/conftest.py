"""Pruebas de integración: levantan los 13 microservicios reales (uvicorn en hilos) con SQLite
temporal y los prueban por HTTP, igual que lo haría el frontend."""
import os
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest

_TMP = Path(tempfile.mkdtemp(prefix="boleteria_test_"))
BASE_PUERTO = 18000

# Las variables deben fijarse ANTES de importar la configuración y los servicios.
os.environ.update({
    "DATABASE_URL_TEMPLATE": f"sqlite:///{_TMP}/{{schema}}.db",
    "INTERNAL_API_KEY": "clave-de-pruebas",
    "BCRYPT_ROUNDS": "4",
    "LOGIN_MAX_INTENTOS": "5",
    "SESSION_MINUTES": "60",
    "EXPIRACION_INTERVALO_SEG": "3600",   # en pruebas la expiración se dispara a mano
    "RESERVA_MAX_ASIENTOS": "10",
    "AUTO_CREATE_TABLES": "true",
    "ANALITICA_ETL_MINUTOS": "0",          # en pruebas el ETL se ejecuta a mano
})
from common.config import SERVICIOS  # noqa: E402

for _n, _p in SERVICIOS.items():
    os.environ[f"{_n.upper()}_URL"] = f"http://127.0.0.1:{BASE_PUERTO + _p % 100}"
# Compatibilidad: las pruebas de usuarios/acceso permiten fijar su propia BD (MySQL real)
if os.getenv("TEST_USUARIOS_DB"):
    os.environ["USUARIOS_DATABASE_URL"] = os.environ["TEST_USUARIOS_DB"]
if os.getenv("TEST_ACCESO_DB"):
    os.environ["ACCESO_DATABASE_URL"] = os.environ["TEST_ACCESO_DB"]

import importlib  # noqa: E402

import uvicorn  # noqa: E402

URL = {n: os.environ[f"{n.upper()}_URL"] for n in SERVICIOS}
USR, ACC = URL["usuarios"], URL["acceso"]
KEY = {"X-Internal-Key": "clave-de-pruebas"}


def _levantar(app, puerto):
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(200):
        if srv.started:
            return srv
        time.sleep(0.05)
    raise RuntimeError("El servidor no arrancó")


@pytest.fixture(scope="session", autouse=True)
def servidores():
    srvs = [_levantar(importlib.import_module(f"{n}.main").app, BASE_PUERTO + p % 100)
            for n, p in SERVICIOS.items()]
    yield
    for s in srvs:
        s.should_exit = True


_contador = {"n": 0}


def _datos_nuevos(prefijo="ana"):
    _contador["n"] += 1
    n = _contador["n"]
    return {"nombre": "Ana", "apellido": "Pérez", "correo": f"{prefijo}{n}@example.com",
            "telefono": "3001234567", "documento": f"CC{10000000 + n}",
            "contrasena": "Clave1234"}


@pytest.fixture
def datos_usuario():
    return _datos_nuevos()


@pytest.fixture
def registrar(datos_usuario):
    def _hacer(**cambios):
        d = {**datos_usuario, **cambios}
        return httpx.post(f"{USR}/usuarios/registro", json=d)
    return _hacer


def nuevo_usuario(prefijo="usr"):
    """Registra un usuario y abre sesión. Devuelve (datos, token, id_usuario)."""
    d = _datos_nuevos(prefijo)
    r = httpx.post(f"{USR}/usuarios/registro", json=d)
    assert r.status_code == 201, r.text
    t = httpx.post(f"{ACC}/auth/login", json={"correo": d["correo"], "contrasena": d["contrasena"]})
    assert t.status_code == 200, t.text
    return d, t.json()["access_token"], r.json()["id_usuario"]


@pytest.fixture
def usuario_con_token():
    return nuevo_usuario()


def nuevo_admin():
    d, _, id_usuario = nuevo_usuario("admin")
    httpx.put(f"{ACC}/internal/credenciales/{id_usuario}/rol", json={"rol": "administrador"},
              headers=KEY).raise_for_status()
    t = httpx.post(f"{ACC}/auth/login", json={"correo": d["correo"], "contrasena": d["contrasena"]})
    return t.json()["access_token"], id_usuario


@pytest.fixture
def admin_token():
    return nuevo_admin()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
