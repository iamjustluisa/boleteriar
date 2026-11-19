import httpx

from common.config import settings
from common.errors import ServicioNoDisponible


class UsuariosClient:
    def buscar_por_correo(self, correo: str) -> dict | None:
        try:
            r = httpx.get(f"{settings.usuarios_url}/internal/usuarios/por-correo",
                          params={"correo": correo},
                          headers={"X-Internal-Key": settings.internal_key},
                          timeout=settings.http_timeout)
        except httpx.HTTPError as exc:
            raise ServicioNoDisponible("Usuarios no responde") from exc
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        raise ServicioNoDisponible(f"Usuarios respondió {r.status_code}")


usuarios_client = UsuariosClient()
