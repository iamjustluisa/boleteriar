from common.app import crear_app

from .database import Base, engine, preparar
from .routes import router

app = crear_app("usuarios", "Microservicio de Usuarios",
                "Registro, actualización y consulta de datos personales (RF-USR-01 a 03).",
                router, Base, engine, preparar)
