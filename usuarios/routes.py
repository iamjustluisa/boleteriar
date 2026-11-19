from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.clients import parse_ids
from common.errors import ServicioNoDisponible
from common.security import exigir_clave_interna

from . import service
from .clients import acceso_client
from .database import get_db
from .deps import sesion_actual, solo_administrador
from .models import Usuario
from .schemas import (ActualizarIn, RegistroIn, UsuarioConRolOut, UsuarioInternoOut,
                      UsuarioOut)

router = APIRouter()


# ---------- Públicas / del usuario autenticado ----------
@router.post("/usuarios/registro", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED,
             tags=["Usuarios"], summary="CU-01 Registrar usuario")
def registrar(datos: RegistroIn, db: Session = Depends(get_db)):
    return service.registrar(db, datos)


@router.get("/usuarios/me", response_model=UsuarioOut, tags=["Usuarios"],
            summary="RF-USR-03 Consultar mis datos")
def mi_perfil(sesion: dict = Depends(sesion_actual), db: Session = Depends(get_db)):
    usuario = db.get(Usuario, sesion["id_usuario"])
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return usuario


@router.put("/usuarios/me", response_model=UsuarioOut, tags=["Usuarios"],
            summary="CU-02 Actualizar mis datos de contacto")
def actualizar_mi_perfil(datos: ActualizarIn, sesion: dict = Depends(sesion_actual),
                         db: Session = Depends(get_db)):
    # El id sale de la sesión, nunca del cliente: un usuario solo modifica lo suyo.
    return service.actualizar(db, sesion["id_usuario"], datos)


# ---------- Administración ----------
@router.get("/usuarios", response_model=list[UsuarioConRolOut], tags=["Administración"],
            summary="Listar usuarios (solo administrador)")
def listar(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
           _: dict = Depends(solo_administrador), db: Session = Depends(get_db)):
    usuarios = db.scalars(select(Usuario).order_by(Usuario.id_usuario).limit(limit).offset(offset)).all()
    salida = []
    for u in usuarios:
        item = UsuarioConRolOut.model_validate(u)
        try:
            item.rol = acceso_client.obtener_rol(u.id_usuario)
        except ServicioNoDisponible:
            item.rol = None
        salida.append(item)
    return salida


# ---------- Rutas internas (servicio a servicio) ----------
@router.get("/internal/usuarios/por-correo", response_model=UsuarioInternoOut,
            dependencies=[Depends(exigir_clave_interna)], tags=["Interno"], include_in_schema=False)
def interno_por_correo(correo: str, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo.strip().lower()))
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe")
    return usuario


@router.get("/internal/usuarios", response_model=list[UsuarioOut],
            dependencies=[Depends(exigir_clave_interna)], tags=["Interno"], include_in_schema=False)
def interno_varios(ids: str = "", db: Session = Depends(get_db)):
    lista = parse_ids(ids)
    if not lista:
        return []
    return db.scalars(select(Usuario).where(Usuario.id_usuario.in_(lista))).all()


@router.get("/internal/usuarios/{id_usuario}", response_model=UsuarioOut,
            dependencies=[Depends(exigir_clave_interna)], tags=["Interno"], include_in_schema=False)
def interno_por_id(id_usuario: int, db: Session = Depends(get_db)):
    usuario = db.get(Usuario, id_usuario)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe")
    return usuario
