from common.app import crear_app

from .database import Base, SessionLocal, engine, preparar
from .routes import router
from .seed import sembrar


def _sembrar() -> None:
    with SessionLocal() as db:
        sembrar(db)


app = crear_app("acceso", "Microservicio de Control de Acceso",
                "Autenticación, sesiones, roles y permisos (RF-ACC-01 a 03).",
                router, Base, engine, preparar, al_iniciar=_sembrar)
