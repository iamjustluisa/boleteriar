from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.config import settings
from common.security import exigir_clave_interna

from . import service
from .database import get_db
from .deps import sesion_actual, solo_administrador, token_actual
from .models import Credencial, Permiso, Rol
from .schemas import (AsignarRolIn, CredencialInternaIn, PermisoOut, RolOut, SesionInternaOut,
                      SesionOut, TokenInternoIn, TokenOut, LoginIn)

router = APIRouter()


# ---------- Autenticación ----------
@router.post("/auth/login", response_model=TokenOut, tags=["Autenticación"],
             summary="CU-03 Iniciar sesión")
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "desconocida"
    token, _sesion, cred = service.login(db, datos.correo, datos.contrasena, ip)
    return TokenOut(access_token=token, expira_en=settings.session_minutes * 60,
                    id_usuario=cred.id_usuario, rol=cred.rol.nombre)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Autenticación"],
             summary="CU-03 Cerrar sesión")
def logout(token: str = Depends(token_actual), db: Session = Depends(get_db)):
    service.logout(db, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=SesionOut, tags=["Autenticación"],
            summary="Datos de la sesión actual (usuario, rol y permisos)")
def me(info: dict = Depends(sesion_actual)):
    return info


# ---------- Roles y permisos (administrador) ----------
@router.get("/roles", response_model=list[RolOut], tags=["Roles y permisos"],
            summary="Listar roles con sus permisos")
def roles(_: dict = Depends(solo_administrador), db: Session = Depends(get_db)):
    return [RolOut(id_rol=r.id_rol, nombre=r.nombre, descripcion=r.descripcion,
                   permisos=sorted(p.nombre for p in r.permisos))
            for r in db.scalars(select(Rol).order_by(Rol.id_rol)).all()]


@router.get("/permisos", response_model=list[PermisoOut], tags=["Roles y permisos"],
            summary="Listar permisos")
def permisos(_: dict = Depends(solo_administrador), db: Session = Depends(get_db)):
    return db.scalars(select(Permiso).order_by(Permiso.id_permiso)).all()


@router.put("/credenciales/{id_usuario}/rol", tags=["Roles y permisos"],
            summary="CU-04 Asignar rol a un usuario")
def asignar_rol(id_usuario: int, datos: AsignarRolIn, actor: dict = Depends(solo_administrador),
                db: Session = Depends(get_db)):
    cred = service.asignar_rol(db, id_usuario, datos.rol, actor["id_usuario"])
    return {"id_usuario": cred.id_usuario, "rol": cred.rol.nombre}


# ---------- Rutas internas (servicio a servicio) ----------
@router.post("/internal/credenciales", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(exigir_clave_interna)], include_in_schema=False)
def interno_crear_credencial(datos: CredencialInternaIn, db: Session = Depends(get_db)):
    cred = service.crear_credencial(db, datos.id_usuario, datos.contrasena, datos.rol)
    return {"id_credencial": cred.id_credencial}


@router.post("/internal/sesiones/validar", response_model=SesionInternaOut,
             dependencies=[Depends(exigir_clave_interna)], include_in_schema=False)
def interno_validar(datos: TokenInternoIn, db: Session = Depends(get_db)):
    info = service.validar_token(db, datos.token)
    if info is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida")
    return info


@router.get("/internal/credenciales/{id_usuario}", dependencies=[Depends(exigir_clave_interna)],
            include_in_schema=False)
def interno_rol(id_usuario: int, db: Session = Depends(get_db)):
    cred = db.scalar(select(Credencial).where(Credencial.id_usuario == id_usuario))
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe")
    return {"id_usuario": id_usuario, "rol": cred.rol.nombre, "estado": cred.estado}


@router.put("/internal/credenciales/{id_usuario}/rol", dependencies=[Depends(exigir_clave_interna)],
            include_in_schema=False)
def interno_asignar_rol(id_usuario: int, datos: AsignarRolIn, db: Session = Depends(get_db)):
    """Uso operativo (script de datos iniciales): promover el primer administrador."""
    cred = service.asignar_rol(db, id_usuario, datos.rol, None)
    return {"id_usuario": cred.id_usuario, "rol": cred.rol.nombre}
