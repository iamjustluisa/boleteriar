"""Registro de auditoría (CU-22, RF-AUD-01, RN19).

Cada operación crítica se envía al microservicio de Auditoría en segundo plano: una falla de
auditoría nunca frena la operación principal. También queda en consola con prefijo AUDITORIA.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from .security import utcnow

_log = logging.getLogger("auditoria")
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("AUDITORIA %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="auditoria")


def _enviar(registro: dict) -> None:
    from .clients import auditoria  # import tardío para evitar ciclos
    try:
        auditoria.post("/internal/auditoria", registro)
    except Exception as exc:
        _log.warning("No se pudo enviar al microservicio de Auditoría: %s", exc)


def registrar(accion: str, entidad: str, id_entidad: int | None = None,
              id_usuario: int | None = None, detalle: str | None = None) -> None:
    try:
        registro = {"fecha_hora": utcnow().isoformat(timespec="seconds"), "id_usuario": id_usuario,
                    "accion": accion, "entidad": entidad, "id_entidad": id_entidad,
                    "detalle": (detalle or None) and str(detalle)[:255]}
        _log.info(json.dumps(registro, ensure_ascii=False))
        _pool.submit(_enviar, registro)
    except Exception:
        pass


def esperar_pendientes(timeout: float = 5) -> None:
    """Usado por las pruebas para esperar que los registros lleguen."""
    import time
    fin = time.time() + timeout
    while _pool._work_queue.qsize() and time.time() < fin:  # noqa: SLF001
        time.sleep(0.05)
    time.sleep(0.2)
