"""Configuración compartida por los 13 microservicios transaccionales y el de analítica. Todo se lee de variables de entorno (.env).

Bases de datos
--------------
Cada microservicio usa su propio esquema (``esquema_<servicio>``). La URL se arma así:

1. ``<SERVICIO>_DATABASE_URL`` si existe (ej. ``EVENTOS_DATABASE_URL``), si no
2. ``DATABASE_URL_TEMPLATE`` reemplazando ``{schema}`` por ``esquema_<servicio>``.

* MySQL (docker-compose):  ``mysql+pymysql://boleteria:pass@mysql:3306/{schema}?charset=utf8mb4``
  → un *database* de MySQL por microservicio.
* PostgreSQL en la nube (Neon):  ``postgresql+psycopg2://usr:pass@host/neondb?sslmode=require``
  (sin ``{schema}``) → una sola base y un *schema* de PostgreSQL por microservicio.

URLs entre microservicios
-------------------------
``<SERVICIO>_URL`` si existe; si no ``SERVICE_URL_TEMPLATE`` con ``{nombre}`` y ``{puerto}``.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_CLAVE_POR_DEFECTO = "cambiar-esta-clave-interna"

# Nombre del microservicio -> puerto en desarrollo local
SERVICIOS: dict[str, int] = {
    "usuarios": 8001,
    "acceso": 8002,
    "escenarios": 8003,
    "eventos": 8004,
    "localidades": 8005,
    "asientos": 8006,
    "disponibilidad": 8007,
    "reservas": 8008,
    "compras": 8009,
    "pagos": 8010,
    "boletas": 8011,
    "notificaciones": 8012,
    "auditoria": 8013,
    "analitica": 8014,   # componente OLAP: Data Warehouse, ETL e indicadores (Sprints 7 y 8)
}


def _bool(nombre: str, defecto: str) -> bool:
    return os.getenv(nombre, defecto).strip().lower() in ("1", "true", "si", "sí", "yes")


class Settings:
    def __init__(self) -> None:
        self.db_template = os.getenv(
            "DATABASE_URL_TEMPLATE",
            "mysql+pymysql://boleteria:boleteria_pass@localhost:3306/{schema}?charset=utf8mb4",
        )
        self.service_url_template = os.getenv("SERVICE_URL_TEMPLATE", "http://localhost:{puerto}")
        self.internal_key = os.getenv("INTERNAL_API_KEY", _CLAVE_POR_DEFECTO)
        # --- Sesiones y contraseñas ---
        self.session_minutes = int(os.getenv("SESSION_MINUTES", "120"))
        self.bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
        self.login_max_intentos = int(os.getenv("LOGIN_MAX_INTENTOS", "5"))
        self.login_ventana_seg = int(os.getenv("LOGIN_VENTANA_SEG", "900"))
        # --- Reglas del negocio configurables ---
        self.reserva_minutos = float(os.getenv("RESERVA_MINUTOS", "10"))          # RN16
        self.reserva_max_asientos = int(os.getenv("RESERVA_MAX_ASIENTOS", "10"))
        self.expiracion_intervalo_seg = float(os.getenv("EXPIRACION_INTERVALO_SEG", "15"))
        self.zona_horaria = os.getenv("ZONA_HORARIA", "America/Bogota")
        # --- Web ---
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
        self.auto_create_tables = _bool("AUTO_CREATE_TABLES", "true")
        self.http_timeout = float(os.getenv("HTTP_TIMEOUT", "15"))
        self.db_pool_size = int(os.getenv("DB_POOL_SIZE", "3"))
        self.db_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "7"))

        if self.internal_key == _CLAVE_POR_DEFECTO:
            logging.getLogger("boleteria").warning(
                "INTERNAL_API_KEY usa el valor por defecto. Defínela en .env antes de desplegar.")

    # ---------- bases de datos ----------
    @staticmethod
    def esquema(servicio: str) -> str:
        return f"esquema_{servicio}"

    def db_url(self, servicio: str) -> str:
        url = os.getenv(f"{servicio.upper()}_DATABASE_URL") or \
            self.db_template.replace("{schema}", self.esquema(servicio))
        # Neon/Render entregan "postgres://" o "postgresql://": se fija el driver instalado (psycopg2)
        for prefijo in ("postgres://", "postgresql://"):
            if url.startswith(prefijo):
                url = "postgresql+psycopg2://" + url[len(prefijo):]
        return url

    def usa_schema_postgres(self, servicio: str) -> bool:
        """True si es PostgreSQL con una sola base: el esquema se maneja con search_path."""
        url = self.db_url(servicio)
        return url.startswith("postgres") and "{schema}" not in self.db_template \
            and not os.getenv(f"{servicio.upper()}_DATABASE_URL")

    # ---------- URLs entre microservicios ----------
    def url(self, servicio: str) -> str:
        propia = os.getenv(f"{servicio.upper()}_URL")
        if propia:
            return propia.rstrip("/")
        return self.service_url_template.format(
            nombre=servicio, puerto=SERVICIOS[servicio]).rstrip("/")

    # Compatibilidad con la primera instancia (usuarios / acceso)
    @property
    def usuarios_url(self) -> str:
        return self.url("usuarios")

    @property
    def acceso_url(self) -> str:
        return self.url("acceso")


settings = Settings()
