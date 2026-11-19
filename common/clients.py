"""Cliente HTTP genérico entre microservicios.

Cada microservicio guarda solo el *id* de las entidades de otros servicios (referencias lógicas,
Tabla 61). Antes de guardar, el servicio de origen consulta al de destino con estas llamadas.
Todas las rutas ``/internal/*`` exigen la cabecera ``X-Internal-Key``.
"""
import httpx

from .config import settings
from .errors import ErrorServicio, ServicioNoDisponible

_http = httpx.Client(timeout=settings.http_timeout,
                     limits=httpx.Limits(max_connections=200, max_keepalive_connections=50))


def _detalle(r: httpx.Response):
    try:
        d = r.json().get("detail")
        if isinstance(d, list):  # errores de validación de FastAPI
            return "; ".join(str(e.get("msg", e)) for e in d)
        if isinstance(d, dict):  # detalle estructurado (ej. asientos en conflicto)
            return d
        return str(d) if d else r.text
    except Exception:
        return r.text or f"Error {r.status_code}"


class Servicio:
    def __init__(self, nombre: str) -> None:
        self.nombre = nombre

    @property
    def base(self) -> str:
        return settings.url(self.nombre)

    def _req(self, metodo: str, ruta: str, **kw):
        headers = {"X-Internal-Key": settings.internal_key, **kw.pop("headers", {})}
        try:
            r = _http.request(metodo, f"{self.base}{ruta}", headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise ServicioNoDisponible(f"El microservicio de {self.nombre} no responde") from exc
        if r.status_code >= 400:
            raise ErrorServicio(r.status_code, _detalle(r), self.nombre)
        if not r.content:
            return None
        return r.json()

    def get(self, ruta: str, **params):
        return self._req("GET", ruta, params={k: v for k, v in params.items() if v is not None})

    def get_o_none(self, ruta: str, **params):
        try:
            return self.get(ruta, **params)
        except ErrorServicio as e:
            if e.status == 404:
                return None
            raise

    def post(self, ruta: str, json: dict | None = None):
        return self._req("POST", ruta, json=json or {})

    def put(self, ruta: str, json: dict | None = None):
        return self._req("PUT", ruta, json=json or {})


def ids_param(ids) -> str:
    """Lista de ids -> '1,2,3' para pasar por query string."""
    return ",".join(str(int(i)) for i in sorted(set(ids)))


def parse_ids(texto: str | None) -> list[int]:
    if not texto:
        return []
    salida = []
    for parte in texto.split(","):
        parte = parte.strip()
        if parte.isdigit():
            salida.append(int(parte))
    return salida


usuarios = Servicio("usuarios")
acceso = Servicio("acceso")
escenarios = Servicio("escenarios")
eventos = Servicio("eventos")
localidades = Servicio("localidades")
asientos = Servicio("asientos")
disponibilidad = Servicio("disponibilidad")
reservas = Servicio("reservas")
compras = Servicio("compras")
pagos = Servicio("pagos")
boletas = Servicio("boletas")
notificaciones = Servicio("notificaciones")
auditoria = Servicio("auditoria")
