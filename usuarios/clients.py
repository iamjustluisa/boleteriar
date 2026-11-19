"""Cliente HTTP hacia Control de Acceso (referencia lógica entre microservicios)."""
import httpx

from common.config import settings
from common.errors import ErrorServicio, ServicioNoDisponible


class AccesoClient:
    def _headers(self) -> dict:
        return {"X-Internal-Key": settings.internal_key}

    def _post(self, ruta: str, json: dict) -> httpx.Response:
        try:
            return httpx.post(f"{settings.acceso_url}{ruta}", json=json,
                              headers=self._headers(), timeout=settings.http_timeout)
        except httpx.HTTPError as exc:
            raise ServicioNoDisponible("Control de Acceso no responde") from exc

    def crear_credencial(self, id_usuario: int, contrasena: str, rol: str = "usuario") -> None:
        r = self._post("/internal/credenciales",
                       {"id_usuario": id_usuario, "contrasena": contrasena, "rol": rol})
        if r.status_code >= 400:
            raise ErrorServicio(r.status_code, r.text)

    def validar_token(self, token: str) -> dict | None:
        """Devuelve {id_usuario, rol, permisos, ...} o None si la sesión no es válida."""
        r = self._post("/internal/sesiones/validar", {"token": token})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 401:
            return None
        raise ErrorServicio(r.status_code, r.text)

    def obtener_rol(self, id_usuario: int) -> str | None:
        try:
            r = httpx.get(f"{settings.acceso_url}/internal/credenciales/{id_usuario}",
                          headers=self._headers(), timeout=settings.http_timeout)
        except httpx.HTTPError as exc:
            raise ServicioNoDisponible("Control de Acceso no responde") from exc
        return r.json().get("rol") if r.status_code == 200 else None


acceso_client = AccesoClient()
