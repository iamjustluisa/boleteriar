from sqlalchemy.orm import DeclarativeBase

from common.db import build_db


class Base(DeclarativeBase):
    pass


# Data Warehouse (esquema_analitica). Puede estar en otro servidor: ANALITICA_DATABASE_URL.
engine, SessionLocal, get_db, preparar = build_db("analitica")
