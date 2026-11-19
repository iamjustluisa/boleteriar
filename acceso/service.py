import hashlib
import secrets
from datetime import timedelta

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common import auditoria
from common.config import settings
from common.errors import ServicioNoDisponible
from common.security import utcnow

from .clients import usuarios_client
from .models import Credencial, Rol, Sesion
from .ratelimit import LimiteIntentos

limite_login = LimiteIntentos(settings.login_max_intentos, settings.login_ventana_seg)

ROL_ADMIN = "administrador"
_MSG_CREDENCIALES = "Credenciales inválidas"


# ---------- contraseñas y tokens ----------
def hash_contrasena(plana: str) -> str:
    return bcrypt.hashpw(plana.encode("utf-8"), bcrypt.gensalt(settings.bcrypt_rounds)).decode()


def verificar_contrasena(plana: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(plana.encode("utf-8")[:72], hash_.encode())
    except ValueError:
        return False


# Hash de relleno: si el correo no existe se hace igualmente un bcrypt, así el tiempo de
# respuesta no delata qué correos están registrados.
_HASH_RELLENO = hash_contrasena("relleno-no-valido-1")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- credenciales (invocado por Usuarios) ----------
def crear_credencial(db: Session, id_usuario: int, contrasena: str, nombre_rol: str) -> Credencial:
    rol = db.scalar(select(Rol).where(Rol.nombre == nombre_rol))
    if rol is None:
        raise HTTPException(422, f"El rol '{nombre_rol}' no existe")
    if db.scalar(select(Credencial).where(Credencial.id_usuario == id_usuario)):
        raise HTTPException(status.HTTP_409_CONFLICT, "El usuario ya tiene credencial")
    cred = Credencial(id_usuario=id_usuario, id_rol=rol.id_rol, estado="activa",
                      contrasena_hash=hash_contrasena(contrasena))
    db.add(cred)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "El usuario ya tiene credencial")
    return cred


# ---------- login / logout (CU-03) ----------
def login(db: Session, correo: str, contrasena: str, ip: str) -> tuple[str, Sesion, Credencial]:
    clave = f"{ip}|{correo}"
    espera = limite_login.segundos_restantes(clave)
    if espera:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Demasiados intentos fallidos. Intenta de nuevo más tarde.",
                            headers={"Retry-After": str(espera)})

    try:
        usuario = usuarios_client.buscar_por_correo(correo)
    except ServicioNoDisponible:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "El servicio no está disponible. Intenta de nuevo.")

    cred = None
    if usuario is not None:
        cred = db.scalar(select(Credencial).where(Credencial.id_usuario == usuario["id_usuario"]))

    hash_a_comparar = cred.contrasena_hash if cred else _HASH_RELLENO
    correcta = verificar_contrasena(contrasena, hash_a_comparar)

    if not (cred and correcta and cred.estado == "activa"):
        limite_login.fallo(clave)
        auditoria.registrar("LOGIN_FALLIDO", "SESION", None,
                            cred.id_usuario if cred else None,
                            "credencial bloqueada" if cred and correcta else "credenciales inválidas")
        # Mismo mensaje exista o no el correo (CU-03: no revelar si el correo existe)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _MSG_CREDENCIALES)

    limite_login.exito(clave)
    token = secrets.token_urlsafe(32)
    sesion = Sesion(id_credencial=cred.id_credencial, token=_hash_token(token),
                    fecha_inicio=utcnow(), estado="activa")
    db.add(sesion)
    db.commit()
    auditoria.registrar("LOGIN_OK", "SESION", sesion.id_sesion, cred.id_usuario)
    return token, sesion, cred


def validar_token(db: Session, token: str) -> dict | None:
    """Devuelve los datos de la sesión si el token es válido y vigente; si no, None."""
    sesion = db.scalar(select(Sesion).where(Sesion.token == _hash_token(token)))
    if sesion is None or sesion.estado != "activa":
        return None
    if utcnow() > sesion.fecha_inicio + timedelta(minutes=settings.session_minutes):
        sesion.estado, sesion.fecha_fin = "expirada", utcnow()
        db.commit()
        return None
    cred = sesion.credencial
    if cred.estado != "activa":
        return None
    return {"id_sesion": sesion.id_sesion, "id_usuario": cred.id_usuario, "rol": cred.rol.nombre,
            "permisos": sorted(p.nombre for p in cred.rol.permisos)}


def logout(db: Session, token: str) -> None:
    sesion = db.scalar(select(Sesion).where(Sesion.token == _hash_token(token)))
    if sesion and sesion.estado == "activa":
        sesion.estado, sesion.fecha_fin = "cerrada", utcnow()
        db.commit()
        auditoria.registrar("LOGOUT", "SESION", sesion.id_sesion, sesion.credencial.id_usuario)


# ---------- roles (CU-04) ----------
def asignar_rol(db: Session, id_usuario: int, nombre_rol: str, actor: int | None) -> Credencial:
    cred = db.scalar(select(Credencial).where(Credencial.id_usuario == id_usuario))
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El usuario no tiene credencial")
    rol = db.scalar(select(Rol).where(Rol.nombre == nombre_rol))
    if rol is None:
        raise HTTPException(422, f"El rol '{nombre_rol}' no existe")

    if cred.rol.nombre == ROL_ADMIN and nombre_rol != ROL_ADMIN:
        # Siempre debe quedar al menos un administrador activo (bloqueo de filas para evitar carreras)
        admins = db.scalars(select(Credencial).join(Rol).where(
            Rol.nombre == ROL_ADMIN, Credencial.estado == "activa").with_for_update()).all()
        if len(admins) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Debe existir al menos un administrador")

    anterior = cred.rol.nombre
    cred.id_rol = rol.id_rol
    db.commit()
    db.refresh(cred)
    auditoria.registrar("ASIGNAR_ROL", "CREDENCIAL", cred.id_credencial, actor,
                        f"usuario {id_usuario}: {anterior} -> {nombre_rol}")
    return cred


def promover_a_admin(db: Session, id_usuario: int) -> None:
    """Uso operativo (script de arranque): salta la validación de quién solicita."""
    asignar_rol(db, id_usuario, ROL_ADMIN, None)
