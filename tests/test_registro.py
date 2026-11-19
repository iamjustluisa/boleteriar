import httpx
import pytest

from .conftest import ACC, USR


def test_registro_valido(registrar):
    r = registrar()
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["id_usuario"] > 0
    assert "contrasena" not in cuerpo and "contrasena_hash" not in cuerpo


def test_correo_duplicado_rechazado(registrar, datos_usuario):
    assert registrar().status_code == 201
    r = registrar(documento="OTRO123456")           # mismo correo
    assert r.status_code == 409 and "correo" in r.json()["detail"].lower()


def test_correo_duplicado_sin_importar_mayusculas(registrar, datos_usuario):
    assert registrar().status_code == 201
    r = registrar(correo=datos_usuario["correo"].upper(), documento="OTRO123456")
    assert r.status_code == 409


def test_documento_duplicado_rechazado(registrar, datos_usuario):
    assert registrar().status_code == 201
    r = registrar(correo="otro@example.com")        # mismo documento
    assert r.status_code == 409 and "documento" in r.json()["detail"].lower()


@pytest.mark.parametrize("campo", ["nombre", "apellido", "correo", "telefono", "documento", "contrasena"])
def test_campo_obligatorio(datos_usuario, campo):
    d = {k: v for k, v in datos_usuario.items() if k != campo}
    assert httpx.post(f"{USR}/usuarios/registro", json=d).status_code == 422


@pytest.mark.parametrize("cambio", [
    {"correo": "no-es-correo"},
    {"telefono": "abc"},
    {"documento": "12"},
    {"contrasena": "corta1"},
    {"contrasena": "sololetrasaaaa"},
    {"contrasena": "123456789"},
    {"contrasena": "a1" * 40},                      # > 72 bytes
    {"nombre": "   "},
])
def test_datos_invalidos(registrar, cambio):
    assert registrar(**cambio).status_code == 422


def test_no_se_puede_registrar_con_rol(datos_usuario):
    """Un cliente no puede elegir su rol: el campo extra se rechaza."""
    r = httpx.post(f"{USR}/usuarios/registro", json={**datos_usuario, "rol": "administrador"})
    assert r.status_code == 422


def test_nuevo_usuario_tiene_rol_usuario(usuario_con_token):
    _, token, _ = usuario_con_token
    me = httpx.get(f"{ACC}/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["rol"] == "usuario"
    assert "gestionar_roles" not in me["permisos"]


def test_contrasena_guardada_como_hash(registrar, datos_usuario):
    r = registrar()
    from acceso.database import SessionLocal
    from acceso.models import Credencial
    from sqlalchemy import select
    with SessionLocal() as db:
        cred = db.scalar(select(Credencial).where(Credencial.id_usuario == r.json()["id_usuario"]))
        assert cred.contrasena_hash != datos_usuario["contrasena"]
        assert cred.contrasena_hash.startswith("$2")        # bcrypt
        assert datos_usuario["contrasena"] not in cred.contrasena_hash
