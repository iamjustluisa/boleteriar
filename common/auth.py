"""Autenticación para todos los microservicios (excepto Control de Acceso, que valida localmente).

Cada petición protegida envía ``Authorization: Bearer <token>``. El servicio pregunta a Control de
Acceso si la sesión es válida y obtiene el id del usuario, su rol y sus permisos (RF-ACC-02, RN20).
No se usa caché: una sesión cerrada deja de aceptarse de inmediato en todos los servicios (RF-ACC-03).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from .clients import acceso
from .errors import ErrorServicio, ServicioNoDisponible
from .security import bearer_scheme


def sesion_actual(cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict:
    if cred is None or not cred.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return acceso.post("/internal/sesiones/validar", {"token": cred.credentials})
    except ErrorServicio as e:
        if e.status == 401:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión expiró. Inicia sesión de nuevo",
                                headers={"WWW-Authenticate": "Bearer"})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No fue posible validar la sesión")
    except ServicioNoDisponible:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Control de Acceso no responde. Intenta de nuevo.")


def requiere(permiso: str):
    """Dependencia que exige un permiso concreto (tabla ROL_PERMISO)."""
    def _dep(info: dict = Depends(sesion_actual)) -> dict:
        if permiso not in info.get("permisos", []):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "No tienes permiso para esta operación (requiere administrador)"
                                if permiso.startswith(("gestionar", "listar", "consultar_aud"))
                                else "No tienes permiso para esta operación")
        return info
    return _dep


def es_admin(info: dict) -> bool:
    return info.get("rol") == "administrador"


def solo_administrador(info: dict = Depends(sesion_actual)) -> dict:
    if not es_admin(info):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol administrador")
    return info
