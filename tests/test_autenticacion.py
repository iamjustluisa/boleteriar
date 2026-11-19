from datetime import timedelta

import httpx

from .conftest import ACC, USR, auth


def _login(correo, contrasena):
    return httpx.post(f"{ACC}/auth/login", json={"correo": correo, "contrasena": contrasena})


def test_login_valido_emite_sesion(usuario_con_token):
    datos, token, id_usuario = usuario_con_token
    r = _login(datos["correo"], datos["contrasena"])
    assert r.status_code == 200
    c = r.json()
    assert c["id_usuario"] == id_usuario and c["rol"] == "usuario"
    assert c["token_type"] == "bearer" and len(c["access_token"]) >= 32


def test_login_correo_no_distingue_mayusculas(usuario_con_token):
    datos, _, _ = usuario_con_token
    assert _login(datos["correo"].upper(), datos["contrasena"]).status_code == 200


def test_contrasena_erronea_y_correo_inexistente_dan_el_mismo_error(usuario_con_token):
    datos, _, _ = usuario_con_token
    mala = _login(datos["correo"], "ClaveEquivocada1")
    fantasma = _login("nadie@example.com", "ClaveEquivocada1")
    assert mala.status_code == fantasma.status_code == 401
    assert mala.json() == fantasma.json()          # no revela si el correo existe


def test_token_se_guarda_hasheado(usuario_con_token):
    _, token, _ = usuario_con_token
    from acceso.database import SessionLocal
    from acceso.models import Sesion
    from sqlalchemy import select
    with SessionLocal() as db:
        guardados = db.scalars(select(Sesion.token)).all()
    assert token not in guardados


def test_perfil_requiere_sesion():
    assert httpx.get(f"{USR}/usuarios/me").status_code == 401
    assert httpx.get(f"{USR}/usuarios/me", headers=auth("token-falso")).status_code == 401
    assert httpx.get(f"{ACC}/auth/me").status_code == 401


def test_consultar_mis_datos(usuario_con_token):
    datos, token, _ = usuario_con_token
    r = httpx.get(f"{USR}/usuarios/me", headers=auth(token))
    assert r.status_code == 200 and r.json()["correo"] == datos["correo"]


def test_logout_invalida_la_sesion(usuario_con_token):
    _, token, _ = usuario_con_token
    assert httpx.get(f"{USR}/usuarios/me", headers=auth(token)).status_code == 200
    assert httpx.post(f"{ACC}/auth/logout", headers=auth(token)).status_code == 204
    assert httpx.get(f"{USR}/usuarios/me", headers=auth(token)).status_code == 401
    assert httpx.get(f"{ACC}/auth/me", headers=auth(token)).status_code == 401


def test_sesion_expirada_se_rechaza(usuario_con_token):
    _, token, _ = usuario_con_token
    from acceso.database import SessionLocal
    from acceso.models import Sesion
    from sqlalchemy import select
    with SessionLocal() as db:
        for s in db.scalars(select(Sesion).where(Sesion.estado == "activa")).all():
            s.fecha_inicio = s.fecha_inicio - timedelta(hours=5)
        db.commit()
    assert httpx.get(f"{USR}/usuarios/me", headers=auth(token)).status_code == 401
    with SessionLocal() as db:
        assert "expirada" in db.scalars(select(Sesion.estado)).all()


def test_credencial_bloqueada_no_inicia_sesion(usuario_con_token):
    datos, token, id_usuario = usuario_con_token
    from acceso.database import SessionLocal
    from acceso.models import Credencial
    from sqlalchemy import select
    with SessionLocal() as db:
        c = db.scalar(select(Credencial).where(Credencial.id_usuario == id_usuario))
        c.estado = "bloqueada"
        db.commit()
    assert _login(datos["correo"], datos["contrasena"]).status_code == 401
    assert httpx.get(f"{USR}/usuarios/me", headers=auth(token)).status_code == 401  # sesión previa también


def test_bloqueo_temporal_tras_intentos_fallidos(usuario_con_token):
    datos, _, _ = usuario_con_token
    for _ in range(5):
        assert _login(datos["correo"], "Mala12345").status_code == 401
    r = _login(datos["correo"], datos["contrasena"])      # ni con la clave correcta
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_rutas_internas_exigen_clave():
    assert httpx.post(f"{ACC}/internal/credenciales",
                      json={"id_usuario": 1, "contrasena": "Clave1234"}).status_code == 403
    assert httpx.get(f"{USR}/internal/usuarios/1").status_code == 403
    assert httpx.post(f"{ACC}/internal/sesiones/validar", json={"token": "x"},
                      headers={"X-Internal-Key": "incorrecta"}).status_code == 403
