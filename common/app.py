"""Fábrica común de aplicaciones FastAPI para los microservicios."""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .errors import ErrorServicio, ServicioNoDisponible

_log = logging.getLogger("boleteria")


def hoy_local() -> date:
    return datetime.now(ZoneInfo(settings.zona_horaria)).date()


def ahora_local() -> datetime:
    return datetime.now(ZoneInfo(settings.zona_horaria)).replace(tzinfo=None)


class _PrefijoGateway:
    """Detrás del gateway (/api/<servicio>) Swagger debe conocer el prefijo para cargar openapi.json."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            for k, v in scope.get("headers", []):
                if k == b"x-forwarded-prefix":
                    scope = {**scope, "root_path": v.decode()}
                    break
        await self.app(scope, receive, send)


def crear_app(servicio: str, titulo: str, descripcion: str, router, base, engine,
              preparar: Callable[[], None], al_iniciar: Callable[[], None] | None = None) -> FastAPI:
    estado = {"listo": False}

    def iniciar() -> None:
        if estado["listo"]:
            return
        preparar()
        if settings.auto_create_tables:
            base.metadata.create_all(engine)
        if al_iniciar:
            al_iniciar()
        estado["listo"] = True
        _log.info("Microservicio %s listo", servicio)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        iniciar()
        yield

    app = FastAPI(title=f"Boletería · {titulo}", version="1.0.0", description=descripcion,
                  lifespan=lifespan)
    app.state.iniciar = iniciar
    app.state.servicio = servicio
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ServicioNoDisponible)
    async def _no_disponible(_: Request, exc: ServicioNoDisponible):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ErrorServicio)
    async def _error_servicio(_: Request, exc: ErrorServicio):
        codigo = exc.status if 400 <= exc.status < 500 and exc.status not in (401, 403) else 502
        return JSONResponse(status_code=codigo, content={"detail": exc.datos or exc.detalle})

    app.include_router(router)
    app.add_middleware(_PrefijoGateway)

    @app.get("/health", tags=["Salud"])
    def health():
        return {"servicio": servicio, "estado": "ok"}

    return app
