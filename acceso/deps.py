from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from common.security import bearer_scheme

from . import service
from .database import get_db


def token_actual(cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if cred is None or not cred.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión requerida",
                            headers={"WWW-Authenticate": "Bearer"})
    return cred.credentials


def sesion_actual(token: str = Depends(token_actual), db: Session = Depends(get_db)) -> dict:
    info = service.validar_token(db, token)
    if info is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada",
                            headers={"WWW-Authenticate": "Bearer"})
    return info


def solo_administrador(info: dict = Depends(sesion_actual)) -> dict:
    if "gestionar_roles" not in info["permisos"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol administrador")
    return info
