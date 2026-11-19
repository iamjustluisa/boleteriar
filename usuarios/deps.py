from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from common.errors import ErrorServicio, ServicioNoDisponible
from common.security import bearer_scheme

from .clients import acceso_client


def sesion_actual(cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict:
    """Valida el token contra Control de Acceso y devuelve los datos de la sesión."""
    if cred is None or not cred.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión requerida",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        info = acceso_client.validar_token(cred.credentials)
    except (ServicioNoDisponible, ErrorServicio):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No fue posible validar la sesión. Intenta de nuevo.")
    if info is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada",
                            headers={"WWW-Authenticate": "Bearer"})
    return info


def solo_administrador(info: dict = Depends(sesion_actual)) -> dict:
    if info.get("rol") != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol administrador")
    return info
