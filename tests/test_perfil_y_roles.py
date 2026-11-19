import httpx

from .conftest import ACC, USR, auth


# ---------- CU-02 Actualizar usuario ----------
def test_actualizar_telefono(usuario_con_token):
    _, token, _ = usuario_con_token
    r = httpx.put(f"{USR}/usuarios/me", json={"telefono": "3109876543"}, headers=auth(token))
    assert r.status_code == 200 and r.json()["telefono"] == "3109876543"


def test_actualizar_correo_y_login_con_el_nuevo(usuario_con_token):
    datos, token, _ = usuario_con_token
    nuevo = "nuevo.correo@example.com"
    assert httpx.put(f"{USR}/usuarios/me", json={"correo": nuevo}, headers=auth(token)).status_code == 200
    assert httpx.post(f"{ACC}/auth/login", json={"correo": nuevo,
                                                 "contrasena": datos["contrasena"]}).status_code == 200
    assert httpx.post(f"{ACC}/auth/login", json={"correo": datos["correo"],
                                                 "contrasena": datos["contrasena"]}).status_code == 401


def test_correo_de_otro_usuario_se_rechaza(usuario_con_token, registrar):
    _, token, _ = usuario_con_token
    registrar(correo="ocupado@example.com", documento="DOC9999999")
    r = httpx.put(f"{USR}/usuarios/me", json={"correo": "ocupado@example.com"}, headers=auth(token))
    assert r.status_code == 409


def test_documento_no_se_puede_modificar(usuario_con_token):
    _, token, _ = usuario_con_token
    r = httpx.put(f"{USR}/usuarios/me", json={"documento": "NUEVO12345"}, headers=auth(token))
    assert r.status_code == 422


def test_actualizar_sin_datos_se_rechaza(usuario_con_token):
    _, token, _ = usuario_con_token
    assert httpx.put(f"{USR}/usuarios/me", json={}, headers=auth(token)).status_code == 422


def test_actualizar_sin_sesion():
    assert httpx.put(f"{USR}/usuarios/me", json={"telefono": "3109876543"}).status_code == 401


# ---------- CU-04 Roles y permisos ----------
def test_usuario_normal_no_puede_administrar(usuario_con_token):
    _, token, id_usuario = usuario_con_token
    assert httpx.get(f"{USR}/usuarios", headers=auth(token)).status_code == 403
    assert httpx.get(f"{ACC}/roles", headers=auth(token)).status_code == 403
    r = httpx.put(f"{ACC}/credenciales/{id_usuario}/rol", json={"rol": "administrador"}, headers=auth(token))
    assert r.status_code == 403            # no puede auto-promoverse


def test_admin_lista_usuarios_con_rol(admin_token, usuario_con_token):
    token, _ = admin_token
    r = httpx.get(f"{USR}/usuarios", headers=auth(token))
    assert r.status_code == 200
    roles = {u["rol"] for u in r.json()}
    assert {"usuario", "administrador"} <= roles


def test_admin_asigna_rol_y_cambia_de_inmediato(admin_token, usuario_con_token):
    token_admin, _ = admin_token
    _, token_u, id_u = usuario_con_token
    r = httpx.put(f"{ACC}/credenciales/{id_u}/rol", json={"rol": "administrador"}, headers=auth(token_admin))
    assert r.status_code == 200 and r.json()["rol"] == "administrador"
    assert httpx.get(f"{USR}/usuarios", headers=auth(token_u)).status_code == 200   # sesión previa ya es admin
    # y se puede volver a degradar mientras exista otro administrador
    r = httpx.put(f"{ACC}/credenciales/{id_u}/rol", json={"rol": "usuario"}, headers=auth(token_admin))
    assert r.status_code == 200


def test_rol_inexistente(admin_token, usuario_con_token):
    token_admin, _ = admin_token
    _, _, id_u = usuario_con_token
    r = httpx.put(f"{ACC}/credenciales/{id_u}/rol", json={"rol": "dios"}, headers=auth(token_admin))
    assert r.status_code == 422


def test_usuario_inexistente(admin_token):
    token_admin, _ = admin_token
    assert httpx.put(f"{ACC}/credenciales/999999/rol", json={"rol": "usuario"},
                     headers=auth(token_admin)).status_code == 404


def test_siempre_debe_quedar_un_administrador():
    """Se prueba en una base aislada de la de otros tests: ver abajo."""
    from acceso import service
    from acceso.database import SessionLocal
    from acceso.models import Credencial, Rol
    from fastapi import HTTPException
    from sqlalchemy import select
    import pytest

    with SessionLocal() as db:
        admins = db.scalars(select(Credencial).join(Rol).where(Rol.nombre == "administrador")).all()
        # Dejar solo uno: degradar a los demás
        for extra in admins[1:]:
            service.asignar_rol(db, extra.id_usuario, "usuario", None)
        ultimo = admins[0]
        with pytest.raises(HTTPException) as e:
            service.asignar_rol(db, ultimo.id_usuario, "usuario", None)
        assert e.value.status_code == 409


def test_roles_y_permisos_sembrados(admin_token):
    token, _ = admin_token
    roles = {r["nombre"]: r for r in httpx.get(f"{ACC}/roles", headers=auth(token)).json()}
    assert set(roles) == {"usuario", "administrador"}
    assert "gestionar_roles" in roles["administrador"]["permisos"]
    assert "gestionar_roles" not in roles["usuario"]["permisos"]
    assert "reservar_asientos" in roles["usuario"]["permisos"]


# ---------- Registro con Acceso caído (saga de compensación) ----------
def test_registro_se_compensa_si_acceso_falla(datos_usuario, monkeypatch):
    from common.errors import ServicioNoDisponible
    from usuarios.clients import acceso_client

    def caido(*a, **k):
        raise ServicioNoDisponible("caído")
    monkeypatch.setattr(acceso_client, "crear_credencial", caido)

    r = httpx.post(f"{USR}/usuarios/registro", json=datos_usuario)
    assert r.status_code == 503
    # el usuario NO quedó guardado: puede reintentar el registro con los mismos datos
    monkeypatch.undo()
    assert httpx.post(f"{USR}/usuarios/registro", json=datos_usuario).status_code == 201
