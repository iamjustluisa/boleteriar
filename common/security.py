"""Utilidades de seguridad compartidas."""
import hmac
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status
from fastapi.security import HTTPBearer

from .config import settings

# auto_error=False: devolvemos nuestro propio 401 en español.
bearer_scheme = HTTPBearer(auto_error=False, description="Token de sesión emitido por /auth/login")


def utcnow() -> datetime:
    """Fecha/hora UTC sin zona (así se guardan en DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def exigir_clave_interna(x_internal_key: str | None = Header(default=None)) -> None:
    """Protege las rutas /internal: solo otros microservicios con la clave compartida."""
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acceso interno denegado")
