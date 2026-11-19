"""Fábrica de motor/sesiones. Cada microservicio crea la suya sobre su propio esquema.

Soporta MySQL/MariaDB (un database por servicio), PostgreSQL (un schema por servicio dentro de
una sola base, ideal para Neon) y SQLite (pruebas).
"""
import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from .config import settings

_log = logging.getLogger("boleteria.db")


def build_db(servicio: str):
    url = settings.db_url(servicio)
    esquema = settings.esquema(servicio)
    kwargs: dict = {"pool_pre_ping": True}
    pg_schema = settings.usa_schema_postgres(servicio)

    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
                      pool_recycle=280)
    if pg_schema:
        kwargs["connect_args"] = {"options": f"-csearch_path={esquema}"}

    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_sqlite(dbapi_conn, _):  # SQLite no aplica FKs si no se le pide
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    def preparar() -> None:
        """Crea el esquema si no existe (PostgreSQL con search_path, o MySQL con permisos)."""
        try:
            if pg_schema:
                base = create_engine(url)
                with base.begin() as c:
                    c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
                base.dispose()
            elif url.startswith("mysql"):
                u = make_url(url)
                if u.database:
                    servidor = create_engine(u.set(database=""))
                    with servidor.begin() as c:
                        c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{u.database}` "
                                       "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                    servidor.dispose()
        except Exception as exc:  # sin permisos: se asume que los scripts SQL ya lo crearon
            _log.info("No se pudo crear el esquema %s automáticamente: %s", esquema, exc)

    return engine, session_local, get_db, preparar
