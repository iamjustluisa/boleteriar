"""API Gateway + frontend.

* Sirve la aplicación web (carpeta ``frontend/``) en ``/``.
* Enruta ``/api/<servicio>/<ruta>`` al microservicio correspondiente, así el navegador habla con
  un único origen (un solo puerto público: ideal para Codespaces o un servidor en la nube).
* Bloquea desde fuera las rutas ``/internal/*`` (solo servicio a servicio).
* ``GET /api/estado``: salud de los 13 microservicios.

Modo todo-en-uno (``MODO_TODO_EN_UNO=true``): los 13 microservicios se montan dentro de este mismo
proceso, cada uno con su propio esquema de base de datos. Sirve para desplegar en un único
contenedor (Render, Railway, Koyeb...) con una base en la nube (Neon). La comunicación entre
servicios sigue siendo HTTP, contra este mismo servidor.
"""
import asyncio
import hmac
import importlib
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

TODO_EN_UNO = os.getenv("MODO_TODO_EN_UNO", "false").lower() in ("1", "true", "si", "yes")
PUERTO = int(os.getenv("PORT", os.getenv("GATEWAY_PORT", "8080")))
if TODO_EN_UNO:
    os.environ.setdefault("SERVICE_URL_TEMPLATE", f"http://127.0.0.1:{PUERTO}/api/{{nombre}}")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from common.config import SERVICIOS, settings  # noqa: E402

_log = logging.getLogger("boleteria.gateway")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
_HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "accept-encoding"}

_cliente: httpx.AsyncClient | None = None
_apps = {}
if TODO_EN_UNO:
    for _nombre in SERVICIOS:
        _apps[_nombre] = importlib.import_module(f"{_nombre}.main").app


def _sembrar_en_segundo_plano() -> None:
    if os.getenv("SEED_AL_INICIAR", "true").lower() not in ("1", "true", "si", "yes"):
        return

    def _correr():
        try:
            from scripts.seed import main as sembrar
            sembrar()
        except Exception as exc:  # nunca debe tumbar el gateway
            _log.warning("Carga de datos de demostración falló: %s", exc)
    threading.Thread(target=_correr, daemon=True, name="seed").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cliente
    _cliente = httpx.AsyncClient(timeout=settings.http_timeout * 2)
    if TODO_EN_UNO:
        import anyio.to_thread
        anyio.to_thread.current_default_thread_limiter().total_tokens = 300
        for nombre, sub in _apps.items():
            await asyncio.to_thread(sub.state.iniciar)
    _sembrar_en_segundo_plano()
    yield
    await _cliente.aclose()


app = FastAPI(title="Boletería · API Gateway", version="1.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def _bloquear_internas(request: Request, call_next):
    """Las rutas /internal solo se aceptan con la clave compartida (llamadas entre servicios)."""
    if "/internal/" in request.url.path:
        clave = request.headers.get("x-internal-key", "")
        if not clave or not hmac.compare_digest(clave, settings.internal_key):
            return JSONResponse({"detail": "No encontrado"}, status_code=404)
    return await call_next(request)


@app.get("/api/estado", tags=["Gateway"])
async def estado():
    async def revisar(nombre: str):
        try:
            r = await _cliente.get(f"{settings.url(nombre)}/health", timeout=4)
            return {"servicio": nombre, "ok": r.status_code == 200, "puerto": SERVICIOS[nombre]}
        except httpx.HTTPError:
            return {"servicio": nombre, "ok": False, "puerto": SERVICIOS[nombre]}
    resultados = await asyncio.gather(*(revisar(n) for n in SERVICIOS))
    motor = settings.db_template.split(":")[0].split("+")[0]
    return {"modo": "todo-en-uno" if TODO_EN_UNO else "microservicios", "base_de_datos": motor,
            "servicios": resultados, "todos_ok": all(r["ok"] for r in resultados)}


if TODO_EN_UNO:
    for _nombre, _sub in _apps.items():
        app.mount(f"/api/{_nombre}", _sub)
else:
    @app.api_route("/api/{servicio}/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(servicio: str, ruta: str, request: Request):
        if servicio not in SERVICIOS:
            return JSONResponse({"detail": f"El servicio «{servicio}» no existe"}, status_code=404)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
        headers["x-forwarded-for"] = request.client.host if request.client else ""
        headers["x-forwarded-prefix"] = f"/api/{servicio}"
        try:
            r = await _cliente.request(request.method, f"{settings.url(servicio)}/{ruta}",
                                       params=request.query_params, content=await request.body(),
                                       headers=headers)
        except httpx.HTTPError:
            return JSONResponse({"detail": f"El microservicio de {servicio} no está disponible"},
                                status_code=503)
        salida = {k: v for k, v in r.headers.items()
                  if k.lower() in ("content-type", "cache-control", "retry-after", "www-authenticate")}
        return Response(r.content, status_code=r.status_code, headers=salida)


# ---------------- Frontend ----------------
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(FRONTEND / "favicon.svg", media_type="image/svg+xml")
