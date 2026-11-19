from sqlalchemy.orm import DeclarativeBase

from common.db import build_db


class Base(DeclarativeBase):
    pass


engine, SessionLocal, get_db, preparar = build_db("disponibilidad")
